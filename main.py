from collections import Counter

def prepare_model(data):
    """Przygotowuje model statystyczny na podstawie danych wejściowych."""
    counts = Counter(data)
    symbols = sorted(counts.keys())
    f = [counts[s] for s in symbols]
    M = sum(f)
    
    cum = [0] * len(f)
    for i in range(1, len(f)):
        cum[i] = cum[i-1] + f[i-1]
        
    s_to_idx = {s: i for i, s in enumerate(symbols)}
    
    # Zwracamy paczkę danych potrzebnych do obu procesów
    return {
        'f': f, 
        'cum': cum, 
        'M': M, 
        'symbols': symbols, 
        's_to_idx': s_to_idx,
        'length': len(data)
    }

def ans_encode(data, model):
    """Zamienia ciąg znaków w jedną dużą liczbę (stan)."""
    state = 1  # Stan początkowy
    f = model['f']
    cum = model['cum']
    M = model['M']
    s_to_idx = model['s_to_idx']
    
    for char in data:
        s = s_to_idx[char]
        # Formuła uANS kodująca
        state = (state // f[s]) * M + cum[s] + (state % f[s])
        
    return state

def ans_decode(state, model):
    """Zamienia liczbę (stan) z powrotem na ciąg znaków."""
    f = model['f']
    cum = model['cum']
    M = model['M']
    symbols = model['symbols']
    length = model['length']
    
    decoded_chars = []
    curr_state = state
    
    for _ in range(length):
        slot = curr_state % M
        
        # Znajdź symbol, do którego należy slot (przeszukiwanie cum)
        s_idx = 0
        for i in range(len(cum)):
            if slot >= cum[i]:
                s_idx = i
            else:
                break
        
        decoded_chars.append(symbols[s_idx])
        
        # Formuła uANS dekodująca (odwrócenie stanu)
        curr_state = f[s_idx] * (curr_state // M) + slot - cum[s_idx]
        
    # ANS działa jak STOS (LIFO), więc odwracamy wynik
    return "".join(reversed(decoded_chars))

# --- PRZYKŁAD UŻYCIA ---

wiadomosc = "abracadabra"
print("Początkowa wiad: ", wiadomosc)
# 1. Tworzymy model na podstawie wiadomości
model = prepare_model(wiadomosc)

# 2. Kodujemy
zakodowana_liczba = ans_encode(wiadomosc, model)
print(f"Zakodowany stan: {zakodowana_liczba}")

# 3. Dekodujemy
odkodowana_wiadomosc = ans_decode(zakodowana_liczba, model)
print(f"Odkodowana wiadomość: {odkodowana_wiadomosc}")