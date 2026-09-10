"""V3 product presentation policy: label status, confidence tiers, top-K assembly.

This module decides *what the product shows*. It never touches a probability.
The number the model produced is the number displayed — the policy only governs
ranking position, wording and how much confidence is claimed around it.

Three deliberate separations:

1. **Label status is presentation, not modelling.** All 44 labels stay in the
   artifacts and in ``all_task_probabilities``. Status only decides what leads.
2. **Confidence is not probability.** A 0.9 probability on a label the Phase-9
   audit showed to be a random event is still DUSUK. Confidence answers "how much
   should you trust this number", which is a different question from "how high is
   this number".
3. **No deterministic maintenance rule and no V2.1 output may enter any of it.**
"""

from __future__ import annotations

import json
import os
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

#: Confidence tiers, in the Turkish the product surface uses. ASCII spellings are
#: the machine values so the API payload is transport-safe; the UI holds the
#: accented display strings.
TIER_HIGH = "YUKSEK"
TIER_MEDIUM = "ORTA"
TIER_LOW = "DUSUK"
TIER_LIMITED_DATA = "SINIRLI_VERI"

TIER_DISPLAY_TR = {
    TIER_HIGH: "YÜKSEK",
    TIER_MEDIUM: "ORTA",
    TIER_LOW: "DÜŞÜK",
    TIER_LIMITED_DATA: "SINIRLI VERİ",
}

PRIMARY, SECONDARY, LOW_CONFIDENCE, HIDDEN = (
    "PRIMARY", "SECONDARY", "LOW_CONFIDENCE", "HIDDEN_BY_DEFAULT")

#: Phase-4 top-K policy. V3 is primarily a ranking system: the product shows a
#: short ranked list, never 44 yes/no flags.
DEFAULT_TOP_K = 3
OPTIONAL_TOP_K = 5
MAX_TOP_K = 10

#: Probability bands used by the confidence tier. These gate *wording*, not the
#: displayed number, and are deliberately conservative.
HIGH_PROBABILITY = 0.60
MEDIUM_PROBABILITY = 0.25

#: Below this share of reconstructable features the answer is data-limited.
MIN_FEATURE_COVERAGE = 0.80
LIMITED_FEATURE_COVERAGE = 0.95

#: Product copy. Kept here so the API, the tests and the UI cannot drift apart.
HEADING_TR = "V3 — EN OLASI 3 SERVİS İŞLEMİ"
SUBHEADING_TR = (
    "V3, 44 işlem arasından bir sonraki tamamlanmış servis kaydında görülme "
    "olasılığı en yüksek olan 3 işlemi öne çıkarır."
)
DISCLAIMER_SYNTHETIC_TR = (
    "Bu tahminler sentetik veri üzerinde doğrulanmıştır. Gerçek filo doğrulaması "
    "henüz yapılmamıştır."
)
DISCLAIMER_NOT_FAILURE_TR = "Bu yüzdeler mekanik arıza olasılığı değildir."
DISCLAIMER_SEPARATE_TR = (
    "Bakım gereksinimi ve bakım aciliyeti deterministik bakım politikasından ayrı "
    "hesaplanır."
)
LOW_CONFIDENCE_HEADER_TR = "Belirsizlik yüksek — öne çıkan olası işlemler"

#: Wording that must never appear on the V3 surface. Asserted by tests over the
#: rendered frontend and over every string this module emits.
FORBIDDEN_COPY = (
    "kesin yapılacak", "kesin yapilacak", "arıza riski", "ariza riski",
    "gerçek veride doğruluk", "gercek veride dogruluk", "accurate", "accuracy",
    "doğruluk oranı", "dogruluk orani",
)


def _ascii_fold(text: str) -> str:
    """Turkish-safe fold for the forbidden-copy check (İ/ı/ğ/ş/ç/ö/ü)."""
    lowered = text.replace("I", "ı").replace("İ", "i").lower()
    swapped = (lowered.replace("ı", "i").replace("ğ", "g").replace("ş", "s")
               .replace("ç", "c").replace("ö", "o").replace("ü", "u"))
    return unicodedata.normalize("NFKD", swapped).encode("ascii", "ignore").decode()


def assert_copy_is_safe(text: str) -> None:
    """Raise if product copy makes a forbidden claim."""
    folded = _ascii_fold(text)
    for bad in FORBIDDEN_COPY:
        if _ascii_fold(bad) in folded:
            raise ValueError(f"forbidden V3 product wording: {bad!r} in {text[:80]!r}")


@dataclass(frozen=True)
class LabelPolicy:
    task_code: str
    display_name_tr: str
    display_name_en: str
    component_group: str
    product_status: str
    support_class: str
    generating_process: str
    test_support: int
    test_pr_auc: float
    test_prevalence: float
    note: str

    @property
    def hidden_by_default(self) -> bool:
        return self.product_status == HIDDEN

    @property
    def reliable(self) -> bool:
        return self.product_status in (PRIMARY, SECONDARY)


@lru_cache(maxsize=4)
def load_label_policy(path: str | None = None) -> dict[str, LabelPolicy]:
    p = Path(path) if path else _default_policy_path()
    raw = json.loads(p.read_text(encoding="utf-8"))
    out = {}
    for r in raw["labels"]:
        out[r["task_code"]] = LabelPolicy(
            task_code=r["task_code"], display_name_tr=r["display_name_tr"],
            display_name_en=r["display_name_en"], component_group=r["component_group"],
            product_status=r["product_status"], support_class=r["support_class"],
            generating_process=r["generating_process"], test_support=int(r["test_support"]),
            test_pr_auc=float(r["test_pr_auc"]), test_prevalence=float(r["test_prevalence"]),
            note=r["note"])
    return out


#: Container deployments have no repository checkout above the package, so the
#: parent walk below finds nothing. This points straight at the policy file.
POLICY_PATH_ENV = "RIDEBASE_V3_LABEL_POLICY"


def _default_policy_path() -> Path:
    env = os.environ.get(POLICY_PATH_ENV)
    if env:
        path = Path(env).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"{POLICY_PATH_ENV}={env} does not exist")
        return path
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "config" / "v3_product_label_policy.json"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "config/v3_product_label_policy.json not found; set "
        f"{POLICY_PATH_ENV} when running outside a repository checkout")


def confidence_tier(probability: float, policy: LabelPolicy,
                    feature_coverage: float = 1.0) -> tuple[str, str]:
    """Deterministic evidence tier for one predicted task. Returns (tier, reason).

    Order matters, and the first two rules exist to stop a large number from
    buying confidence it has not earned:

    1. Thin feature coverage caps everything at SINIRLI_VERI -- if the history
       could not be reconstructed, the probability is an extrapolation.
    2. A HIDDEN_BY_DEFAULT label is DUSUK **regardless of probability**. Phase 9
       showed these are random events; a high score on one is the model being
       confidently wrong, not a strong signal.
    3. LOW_CONFIDENCE labels cap at ORTA even at high probability.
    4. Only then does probability decide, and only PRIMARY labels can reach
       YUKSEK.
    """
    if feature_coverage < MIN_FEATURE_COVERAGE:
        return TIER_LIMITED_DATA, (
            f"feature coverage {feature_coverage:.0%} below {MIN_FEATURE_COVERAGE:.0%} — "
            f"history could not be fully reconstructed at this landmark")
    if policy.hidden_by_default:
        return TIER_LOW, (
            f"{policy.task_code} is generated by a random event process "
            f"({policy.generating_process}); frozen TEST PR-AUC {policy.test_pr_auc:.3f}. "
            f"A high probability here is not evidence.")
    if policy.product_status == LOW_CONFIDENCE:
        tier = TIER_MEDIUM if probability >= HIGH_PROBABILITY else TIER_LOW
        return tier, (
            f"label carries low frozen support ({policy.test_support} TEST positives, "
            f"PR-AUC {policy.test_pr_auc:.3f})")
    if feature_coverage < LIMITED_FEATURE_COVERAGE:
        return TIER_MEDIUM, (
            f"partial feature coverage {feature_coverage:.0%}")
    if policy.product_status == PRIMARY and probability >= HIGH_PROBABILITY:
        return TIER_HIGH, (
            f"PRIMARY label (frozen TEST PR-AUC {policy.test_pr_auc:.3f} on "
            f"{policy.test_support} positives) at probability {probability:.0%}")
    if probability >= MEDIUM_PROBABILITY:
        return TIER_MEDIUM, f"probability {probability:.0%} on a {policy.product_status} label"
    return TIER_LOW, f"probability {probability:.0%} below the {MEDIUM_PROBABILITY:.0%} band"


def rank_tasks(probabilities: dict[str, float], applicable: dict[str, bool],
               policy: dict[str, LabelPolicy], top_k: int = DEFAULT_TOP_K,
               feature_coverage: float = 1.0,
               include_hidden: bool = False) -> list[dict]:
    """Build the ranked product list.

    Hidden-by-default labels are excluded from the product list unless explicitly
    requested; they always remain in ``all_task_probabilities``. Ranking is by
    probability descending with the task code as a deterministic tie-break, so
    two identical inputs always produce byte-identical ordering.
    """
    top_k = max(1, min(int(top_k), MAX_TOP_K))
    rows = []
    for code, p in probabilities.items():
        pol = policy.get(code)
        if pol is None or not applicable.get(code, True):
            continue
        if pol.hidden_by_default and not include_hidden:
            continue
        rows.append((code, float(p), pol))
    rows.sort(key=lambda r: (-r[1], r[0]))

    out = []
    for rank, (code, p, pol) in enumerate(rows[:top_k], start=1):
        tier, reason = confidence_tier(p, pol, feature_coverage)
        out.append({
            "task_code": code,
            "display_name": pol.display_name_tr,
            "display_name_en": pol.display_name_en,
            "component_group": pol.component_group,
            "probability": round(p, 4),
            "percent": round(p * 100, 1),
            "rank": rank,
            "confidence": tier,
            "confidence_display": TIER_DISPLAY_TR[tier],
            "confidence_reason": reason,
            "product_status": pol.product_status,
        })
    return out


def product_warnings(ranked: list[dict], feature_coverage: float,
                     n_inapplicable: int, n_labels: int,
                     hidden_ranked_high: list[str] | None = None) -> list[str]:
    """Warnings that must accompany any V3 payload. The disclaimer is unconditional."""
    w: list[str] = []
    if feature_coverage < MIN_FEATURE_COVERAGE:
        w.append(
            f"Özellik kapsamı düşük ({feature_coverage:.0%}). Bu motosiklet için geçmiş "
            f"veri sınırlı; sonuçlar sınırlı veriyle üretilmiştir.")
    elif feature_coverage < LIMITED_FEATURE_COVERAGE:
        w.append(f"Özellik kapsamı kısmi ({feature_coverage:.0%}).")
    if ranked and all(r["confidence"] in (TIER_LOW, TIER_LIMITED_DATA) for r in ranked):
        w.append(LOW_CONFIDENCE_HEADER_TR)
    for code in hidden_ranked_high or []:
        w.append(
            f"{code} olasılığı yüksek görünüyor ancak bu işlem sentetik veride rastgele "
            f"olay olarak üretilmektedir; güvenilirliği düşüktür.")
    if n_inapplicable:
        w.append(
            f"{n_inapplicable}/{n_labels} işlem bu motosikletin donanımına uygun değil ve "
            f"0.0 olarak sabitlendi.")
    w.append(DISCLAIMER_SYNTHETIC_TR)
    w.append(DISCLAIMER_NOT_FAILURE_TR)
    w.append(DISCLAIMER_SEPARATE_TR)
    for item in w:
        assert_copy_is_safe(item)
    return w
