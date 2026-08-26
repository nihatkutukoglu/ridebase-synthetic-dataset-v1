# RideBase ML

RideBase, motosiklet bakım ve servis süreçlerini temsil eden sentetik,
ilişkisel ve longitudinal bir veri setidir.

## Ana ML Problemleri

1. Bir sonraki servise kalan gün tahmini
2. Bir sonraki servise kalan kilometre tahmini
3. Bir sonraki serviste yapılacak bakım işlemlerinin tahmini
4. Right-censoring / survival analizi

## Proje Yapısı

```
ridebase-ml/
├── data/
│   ├── raw/source_tables/         # Orijinal kaynak tablolar (değiştirilmez)
│   ├── processed/derived_outputs/ # Türetilmiş / ML çıktı tabloları (değiştirilmez)
│   └── interim/                   # Ara işlem çıktıları
├── notebooks/
├── src/{data,features,models,utils}/
├── reports/{figures,tables}/
├── models/
└── outputs/
```

## Notebook Sırası

1. `01_data_understanding.ipynb` — veri setinin dosya yapısını, tablolarını,
   sütunlarını ve temel boyutlarını tanıma.
2. `02_data_quality_and_cleaning.ipynb` — *(eklenecek)*
3. `03_eda.ipynb` — *(eklenecek)*
4. `04_feature_engineering.ipynb` — *(eklenecek)*
5. `05_modeling_*.ipynb` — *(eklenecek)*

## Kurulum

```bash
pip install -r requirements.txt
```
