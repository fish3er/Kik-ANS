"""
Pure Asymmetric Binary System (ABS) Experiment.

Skrypt udowadnia działanie Asymmetric Numeral Systems dla alfabetu
dwusymbolowego (0 i 1). Generuje sztuczny, asymetryczny strumień bitów
i kompresuje go, porównując wynik z teoretyczną granicą Entropii Shannona.
"""

import random
import math
import time

# ── Czysty ABS (Silnik Binarny) ──────────────────────────────────────────────

def abs_compress(bits, p_one, m_bits=16):
    """
    Kompresuje strumień bitów używając Asymmetric Binary System.
    bits  - lista zer i jedynek
    p_one - prawdopodobieństwo wystąpienia jedynki (np. 0.1)
    """
    M = 1 << m_bits
    
    # Model częstotliwości (Dla 2 symboli to prosta proporcja)
    f1 = max(1, int(p_one * M))
    f0 = M - f1
    f = {0: f0, 1: f1}
    cum = {0: 0, 1: f0} # cum[0] to zawsze 0, cum[1] to f0

    state = M
    out_bits = []

    for b in bits:
        freq = f[b]
        
        # Renormalizacja BITOWA (optymalna dla alfabetu dwusymbolowego ABS)
        while state >= 2 * freq:
            out_bits.append(state & 1)
            state >>= 1
            
        # Właściwy krok matematyczny ABS
        state = (state // freq) * M + (state % freq) + cum[b]

    return state, out_bits


def abs_decompress(state, out_bits, p_one, length, m_bits=16):
    """
    Dekoduje strumień z powrotem do oryginalnej listy bitów.
    """
    M = 1 << m_bits
    
    f1 = max(1, int(p_one * M))
    f0 = M - f1
    f = {0: f0, 1: f1}
    cum = {0: 0, 1: f0}

    decoded = []
    ptr = len(out_bits) - 1

    for _ in range(length):
        # Dekodowanie (Brak tablicy lookup! Wystarczy jeden warunek logiczny)
        slot = state & (M - 1)
        b = 1 if slot >= cum[1] else 0
        decoded.append(b)

        # Odwrócenie matematyki ABS
        state = f[b] * (state >> m_bits) + slot - cum[b]

        # Odwrócenie renormalizacji bitowej
        while state < M and ptr >= 0:
            state = (state << 1) | out_bits[ptr]
            ptr -= 1

    # Zwracamy listę w prawidłowej kolejności (odwracamy, bo czytaliśmy od końca)
    return decoded[::-1]


# ── Eksperyment Shannona ──────────────────────────────────────────────────────

def _ms(t): 
    return t * 1000.0

def run_shannon_experiment():
    LENGTH = 2_000_000  # 2 miliony bitów do testu
    P_ONE = 0.1         # Prawdopodobieństwo wystąpienia '1' wynosi 10%
    M_BITS = 16

    print("=" * 65)
    print("--- EKSPERYMENT BINARNY: ABS vs GRANICA SHANNONA ---")
    print("=" * 65)
    
    print("1. Generowanie asymetrycznego strumienia danych...")
    print(f"   Długość strumienia: {LENGTH:,} bitów")
    print(f"   Prawdopodobieństwo jedynki (P1): {P_ONE * 100}%")
    
    t0 = time.perf_counter()
    data = [1 if random.random() < P_ONE else 0 for _ in range(LENGTH)]
    print(f"   Wygenerowano w {_ms(time.perf_counter() - t0):.1f} ms\n")

    # Obliczenia teoretyczne
    entropy = -P_ONE * math.log2(P_ONE) - (1 - P_ONE) * math.log2(1 - P_ONE)
    theoretical_bits = LENGTH * entropy
    
    print("2. Teoria Informacji (Twierdzenie Shannona)")
    print(f"   Entropia źródła:      {entropy:.5f} bita na symbol")
    print(f"   Idealny rozmiar pliku: {theoretical_bits:,.0f} bitów ({theoretical_bits / 8192:.1f} KB)\n")

    print("3. Uruchamianie Asymmetric Binary System (ABS)")
    
    # Kompresja
    t0 = time.perf_counter()
    state, compressed_bits = abs_compress(data, P_ONE, M_BITS)
    enc_ms = _ms(time.perf_counter() - t0)
    
    # Rozmiar to skompresowane bity z tablicy + bity ukryte w finalnym stanie
    final_size_bits = len(compressed_bits) + state.bit_length()
    
    # Dekompresja
    t0 = time.perf_counter()
    decoded = abs_decompress(state, compressed_bits, P_ONE, LENGTH, M_BITS)
    dec_ms = _ms(time.perf_counter() - t0)
    
    is_ok = "ZGODNE" if decoded == data else "BŁĄD DANYCH!"

    # Podsumowanie wyników
    print("-" * 65)
    col = 22
    print(f"{'Metoda':<{col}} | {'Rozmiar (Bity)':>15} | {'Ratio':>8} | {'Status':>8}")
    print("-" * 65)
    
    orig_ratio = 100.0
    print(f"{'Oryginalne dane':<{col}} | {LENGTH:>15,} | {orig_ratio:>7.2f}% | {'-':>8}")
    
    ideal_ratio = (theoretical_bits / LENGTH) * 100
    print(f"{'Idealny limit':<{col}} | {int(theoretical_bits):>15,} | {ideal_ratio:>7.2f}% | {'-':>8}")
    
    abs_ratio = (final_size_bits / LENGTH) * 100
    print(f"{'Wynik kompresji ABS':<{col}} | {final_size_bits:>15,} | {abs_ratio:>7.2f}% | {is_ok:>8}")
    
    print("-" * 65)
    print(f"Dystans do granicy Shannona: zaledwie {abs_ratio - ideal_ratio:.4f} punktu procentowego!")
    print(f"Czasy wykonania: Enc: {enc_ms:.1f} ms | Dec: {dec_ms:.1f} ms")
    print("=" * 65)
    print("Wniosek: Czysta matematyka ABS perfekcyjnie modeluje rozkłady")
    print("         ułamkowe, kompresując nierównomierne dane bitowe bez")
    print("         potrzeby budowania słowników czy tabel lookup.")

if __name__ == "__main__":
    run_shannon_experiment()