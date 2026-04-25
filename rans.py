import collections
import os
import time

class RANS:
    def __init__(self, m_bits=12):
        self.m_bits = m_bits
        self.M = 1 << m_bits
        self.L = 1 << 16  # Dolna granica stanu (musi być >= M)

    def get_model(self, data):
        if not data: return None
        counts = collections.Counter(data)
        total = len(data)
        
        # 1. Skalowanie częstości
        f = [0] * 256
        curr_sum = 0
        for i in range(256):
            if i in counts:
                f[i] = max(1, (counts[i] * self.M) // total)
                curr_sum += f[i]

        # 2. Korekta do sumy M
        while curr_sum != self.M:
            for i in range(256):
                if curr_sum < self.M and f[i] > 0:
                    f[i] += 1
                    curr_sum += 1
                elif curr_sum > self.M and f[i] > 1:
                    f[i] -= 1
                    curr_sum -= 1
                if curr_sum == self.M: break

        # 3. Kumulatywne
        cum = [0] * 257
        for i in range(256):
            cum[i+1] = cum[i] + f[i]
            
        return f, cum

    def compress(self, data, f, cum):
        state = self.L
        bitstream = []
        
        # Limit renormalizacji: state musi być < (L/M) * f * 256
        # przed wykonaniem kroku rANS, aby po kroku stan był < L * 256
        for byte in data:
            freq = f[byte]
            # Renormalizacja w dół (wypychanie bajtów)
            limit = (self.L // self.M) * freq * 256
            while state >= limit:
                bitstream.append(state & 0xFF)
                state >>= 8
            
            # Krok rANS
            state = (state // freq) * self.M + (state % freq) + cum[byte]
            
        return state, bitstream

    def decompress(self, state, bitstream, f, cum, length):
        # Tabela lookup dla przyspieszenia (slot -> symbol)
        lookup = [0] * self.M
        for s in range(256):
            for i in range(cum[s], cum[s+1]):
                lookup[i] = s
        
        decoded = bytearray()
        ptr = len(bitstream) - 1
        
        for _ in range(length):
            slot = state % self.M
            s = lookup[slot]
            decoded.append(s)
            
            # Odwrócenie kroku rANS
            state = f[s] * (state // self.M) + (slot - cum[s])
            
            # Renormalizacja w górę (pobieranie bajtów)
            while state < self.L and ptr >= 0:
                state = (state << 8) | bitstream[ptr]
                ptr -= 1
        
        return bytes(decoded[::-1])

def run_test(folder_path):
    if not os.path.exists(folder_path):
        print(f"Folder {folder_path} nie istnieje!")
        return

    codec = RANS(m_bits=12)
    print(f"{'Plik':<15} | {'Oryginał':>10} | {'Skompresowany':>10} | {'Ratio':>7} | {'Status'}")
    print("-" * 75)

    for fname in sorted(os.listdir(folder_path)):
        fpath = os.path.join(folder_path, fname)
        if not os.path.isfile(fpath): continue
        
        with open(fpath, "rb") as f_in:
            original_data = f_in.read()
        
        if not original_data: continue

        # Model i kompresja
        f, cum = codec.get_model(original_data)
        final_state, stream = codec.compress(original_data, f, cum)
        
        # Rozmiar: stan (8B) + strumień + tabela (256B)
        comp_size = 8 + len(stream) + 256
        ratio = (comp_size / len(original_data)) * 100
        
        # Dekompresja
        reconstructed = codec.decompress(final_state, stream, f, cum, len(original_data))
        
        status = "OK" if original_data == reconstructed else "BŁĄD"
        print(f"{fname[:15]:<15} | {len(original_data):>10} | {comp_size:>10} | {ratio:>6.2f}% | {status}")

# --- URUCHOM TO ---
# Upewnij się, że folder 'silesia' jest w tym samym miejscu co skrypt
run_test("./silesia")