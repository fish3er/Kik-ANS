import os
import zstandard as zstd

def main():
    directory = 'silesia'
    
    # Nagłówek tabeli zgodny ze wzorem
    header = f"{'Plik':<20} | {'Oryginał':>12} | {'Skompresowany':>13} | {'Ratio':>9} | {'Status'}"
    separator = "-" * len(header)
    
    print(header)
    print(separator)

    # Inicjalizacja kompresora (domyślny poziom 3, jak w większości narzędzi)
    cctx = zstd.ZstdCompressor(level=3)

    # Sprawdzenie czy folder istnieje
    if not os.path.exists(directory):
        print(f"Błąd: Folder '{directory}' nie istnieje.")
        return

    # Pobranie listy plików i posortowanie ich
    files = sorted([f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))])

    for filename in files:
        file_path = os.path.join(directory, filename)
        
        try:
            # Odczyt pliku binarnego
            with open(file_path, 'rb') as f:
                original_data = f.read()
            
            orig_size = len(original_data)
            
            # Kompresja
            compressed_data = cctx.compress(original_data)
            comp_size = len(compressed_data)
            
            # Obliczenie ratio (procent wielkości oryginału)
            ratio = (comp_size / orig_size) * 100
            
            # Formatowanie i wyświetlenie wiersza
            # :<20 lewa strona, :>12 prawa strona, :>7.2f format procentowy
            print(f"{filename:<20} | {orig_size:>12} | {comp_size:>13} | {ratio:>8.2f}% | OK")
            
        except Exception as e:
            print(f"{filename:<20} | {'BŁĄD':>12} | {'-':>13} | {'-':>9} | ERROR")

if __name__ == "__main__":
    main()