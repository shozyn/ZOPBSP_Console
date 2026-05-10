# Instalacja i uruchomienie projektu

Projekt wymaga środowiska Python (3.x) oraz zestawu bibliotek zapisanych w pliku `requirements.txt`.  
Poniżej znajduje się instrukcja przygotowania środowiska uruchomieniowego na nowej maszynie.

---

## 1. Utworzenie i aktywacja wirtualnego środowiska (venv)

Zaleca się użycie wirtualnego środowiska, aby odseparować biblioteki projektu od reszty systemu.

Przejdź do katalogu projektu:

```bash
cd /ścieżka/do/projektu

python3 -m venv venv
source venv/bin/activate

pip install --upgrade pip

## Instalacja wymaganych bibliotek
pip install -r requirements.txt

## uruchomienie głównej funkcji:

f_nadrzedna_est_pos_LAUV_3hydrofony.py
