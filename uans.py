import collections
import struct

class UANSCompressor:
    def __init__(self, m_bits=16):
        self.M_BITS = m_bits
        self.M = 1 << m_bits  # Suma częstości (np. 65536)
        self.L = self.M       # Dolna granica stanu

    def get_frequencies(self, data):
        # Liczymy wystąpienia bajtów (0-255)
        counts = collections.Counter(data)
        total = len(data)
        
        # Skalujemy częstości tak, aby suma wynosiła dokładnie M
        f = [0] * 256
        current_sum = 0
        for i in range(256):
            if i in counts:
                # Każdy obecny symbol musi mieć min. 1
                f[i] = max(1, (counts[i] * self.M) // total)
                current_sum += f[i]
        
        # Korekta, aby suma f[i] wynosiła idealnie M
        while current_sum != self.M:
            for i in range(256):
                if current_sum < self.M and f[i] > 0:
                    f[i] += 1
                    current_sum += 1
                elif current_sum > self.M and f[i] > 1:
                    f[i] -= 1
                    current_sum -= 1
                if current_sum == self.M: break

        # Skumulowane częstości
        cum = [0] * 257
        for i in range(256):
            cum[i+1] = cum[i] + f[i]
        return f, cum

    def compress(self, data):
        f, cum = self.get_frequencies(data)
        state = self.L
        bitstream = []

        for byte in data:
            # RENORMALIZACJA (Kodowanie)
            # Jeśli stan jest za duży, wyrzuć bity do bitstreamu
            max_state = (self.L // self.M) * f[byte] * self.M # Uproszczone dla demo
            while state >= (self.L >> 0) * f[byte] * 2: # Warunek bezpieczeństwa
                 bitstream.append(state & 0xFF)
                 state >>= 8

            # Formuła uANS
            state = (state // f[byte]) * self.M + cum[byte] + (state % f[byte])

        return state, bitstream, f

    def decompress(self, final_state, bitstream, f, length):
        # Odtwórz cum
        cum = [0] * 257
        for i in range(256):
            cum[i+1] = cum[i] + f[i]

        state = final_state
        decoded = []
        bitstream_ptr = len(bitstream) - 1

        for _ in range(length):
            slot = state % self.M
            
            # Szukanie symbolu (binary search byłby szybszy)
            byte = 0
            for i in range(256):
                if slot < cum[i+1]:
                    byte = i
                    break
            
            decoded.append(byte)
            
            # Odwrócenie stanu
            state = f[byte] * (state // self.M) + slot - cum[byte]
            
            # RENORMALIZACJA (Dekodowanie)
            while state < self.L and bitstream_ptr >= 0:
                state = (state << 8) | bitstream[bitstream_ptr]
                bitstream_ptr -= 1
                
        return bytes(reversed(decoded))

# --- TEST NA PLIKU ---
# Możesz tu wstawić ścieżkę do pliku z Silesia Corpus, np. "dickens"
input_data = b"Witaj w uANS! To jest test kompresji danych binarnych." 

ans = UANSCompressor(m_bits=12)
state, stream, freqs = ans.compress(input_data)
output_data = ans.decompress(state, stream, freqs, len(input_data))

print(f"Oryginalna długość: {len(input_data)} bajtów")
print(f"Zakodowany stan + strumień: {len(stream) + 4} bajtów") # +4 na stan
print(f"Czy dane są identyczne? {input_data == output_data}")