import collections
import os
import sys
import time

try:
    import zstandard as zstd
except ImportError:
    zstd = None

# ── Shared frequency model ────────────────────────────────────────────────────

def build_model(data, m_bits=16):
    M = 1 << m_bits
    counts = collections.Counter(data)
    total = len(data)
    f = [0] * 256
    curr_sum = 0
    for i in range(256):
        if i in counts:
            f[i] = max(1, (counts[i] * M) // total)
            curr_sum += f[i]
    while curr_sum != M:
        for i in range(256):
            if curr_sum < M and f[i] > 0:
                f[i] += 1; curr_sum += 1
            elif curr_sum > M and f[i] > 1:
                f[i] -= 1; curr_sum -= 1
            if curr_sum == M: break
    cum = [0] * 257
    for i in range(256):
        cum[i+1] = cum[i] + f[i]
    return f, cum

# ── rANS: byte-level renormalization ──────────────────────────────────────────

def rans_compress(data, f, cum, m_bits=16):
    M = 1 << m_bits
    L = 1 << 24
    limit = (L << 8) >> m_bits

    state = L
    out_bytes = bytearray()

    for byte in data:
        freq = f[byte]
        while state >= limit * freq:
            out_bytes.append(state & 0xFF)
            state >>= 8
        state = (state // freq) * M + (state % freq) + cum[byte]
    return state, bytes(out_bytes)

def rans_decompress(state, out_bytes, f, cum, length, m_bits=16):
    M = 1 << m_bits
    L = 1 << 24

    lookup = [0] * M
    for s in range(256):
        for i in range(cum[s], cum[s+1]):
            lookup[i] = s

    decoded = bytearray()
    ptr = len(out_bytes) - 1

    for _ in range(length):
        slot = state & (M - 1)
        s = lookup[slot]
        decoded.append(s)

        state = f[s] * (state >> m_bits) + slot - cum[s]

        while state < L and ptr >= 0:
            state = (state << 8) | out_bytes[ptr]
            ptr -= 1

    return bytes(decoded[::-1])

# ── tANS: table ANS ───────────────────────────────────────────────────────────

def _tans_build_tables(f, cum, m_bits=16):
    M = 1 << m_bits
    sym_of_slot = [0] * M
    step = (M >> 1) + (M >> 3) + 3
    pos = 0

    for s in range(256):
        for _ in range(f[s]):
            sym_of_slot[pos] = s
            pos = (pos + step) & (M - 1)

    dtable_nb   = [0] * M
    dtable_base = [0] * M
    next_x = list(f)

    for slot in range(M):
        s = sym_of_slot[slot]
        x = next_x[s]
        nb = (m_bits + 1) - x.bit_length()
        dtable_nb[slot]   = nb
        dtable_base[slot] = x << nb
        next_x[s] += 1

    etable = [None] * 256
    for s in range(256):
        if f[s] > 0:
            etable[s] = [0] * f[s]

    next_x = list(f)
    for slot in range(M):
        s = sym_of_slot[slot]
        x = next_x[s]
        etable[s][x - f[s]] = M + slot
        next_x[s] += 1

    return sym_of_slot, dtable_nb, dtable_base, etable

def tans_compress(data, f, etable, m_bits=16):
    M = 1 << m_bits
    state = M
    out_bytes = bytearray()
    bit_buf = 0
    bit_count = 0
    total_bits = 0

    for byte in data:
        freq = f[byte]
        x = state
  
        while x >= 2 * freq:
            bit_buf |= (x & 1) << bit_count
            bit_count += 1
            total_bits += 1

            if bit_count == 8:
                out_bytes.append(bit_buf)
                bit_buf = 0
                bit_count = 0

            x >>= 1
        
        state = etable[byte][x - freq]

    if bit_count > 0:
        out_bytes.append(bit_buf)

    return state, bytes(out_bytes), total_bits

def tans_decompress(state, out_bytes, total_bits, sym_of_slot, dtable_nb, dtable_base, length, m_bits=16):
    M = 1 << m_bits
    decoded = bytearray()
    ptr = len(out_bytes) - 1
    bits_in_last = total_bits % 8

    if bits_in_last == 0 and total_bits > 0:
        bits_in_last = 8

    bit_pos = bits_in_last - 1

    for _ in range(length):
        slot = state - M
        s   = sym_of_slot[slot]
        nb  = dtable_nb[slot]
        base = dtable_base[slot]
        decoded.append(s)

        bits_val = 0
        for i in range(nb - 1, -1, -1):
            if ptr >= 0:
                bit = (out_bytes[ptr] >> bit_pos) & 1
                bits_val |= (bit << i)
                bit_pos -= 1
                if bit_pos < 0:
                    ptr -= 1
                    bit_pos = 7

        state = base | bits_val

    return bytes(decoded[::-1])

# ── Comparison runner ─────────────────────────────────────────────────────────

def _ms(t): return t * 1000.0

def run_comparison(folder_path="./silesia"):
    if not os.path.exists(folder_path):
        print(f"Folder '{folder_path}' not found.")
        return
    if zstd is None:
        print("Brak pakietu 'zstandard'. Zainstaluj go komendą: pip install zstandard")
        return

    cctx = zstd.ZstdCompressor(level=3)
    dctx = zstd.ZstdDecompressor()

    col = 15
    print(f"{'File':<{col}} | {'Original':>10} | "
          f"{'-------- rANS (byte renorm) --------':^36} | "
          f"{'----------- tANS (golden spread) -----------':^44} | "
          f"{'------------ zstd ------------':^30}")
    
    print(f"{'':^{col}} | {'':>10} | "
          f"{'Size':>8}  {'Ratio':>6}  {'Enc ms':>7}  {'Dec ms':>7} | "
          f"{'Size':>8}  {'Ratio':>6}  {'Build':>6}  {'Enc ms':>7}  {'Dec ms':>7} | "
          f"{'Size':>8}  {'Ratio':>6}  {'Enc ms':>7}  {'Dec ms':>7}")
    
    sep = "-" * (col + 3 + 12 + 3 + 40 + 3 + 48 + 3 + 34)
    print(sep)

    totals = {k: [0.0, 0.0] for k in ("r", "t", "z")}
    file_count = 0

    for fname in sorted(os.listdir(folder_path)):
        fpath = os.path.join(folder_path, fname)
        if not os.path.isfile(fpath): continue
        with open(fpath, "rb") as fh: data = fh.read()
        if not data: continue

        orig = len(data)
        print(f"  {fname} ({orig / 1e6:.1f} MB) ...", end="", file=sys.stderr, flush=True)
        f, cum = build_model(data)

        # rANS
        t0 = time.perf_counter()
        rs, rbytes = rans_compress(data, f, cum)
        r_enc = _ms(time.perf_counter() - t0)
        r_size = max(1, (rs.bit_length() + 7) // 8) + len(rbytes) + 256
        t0 = time.perf_counter()
        r_ok = "OK" if rans_decompress(rs, rbytes, f, cum, orig) == data else "ERR"
        r_dec = _ms(time.perf_counter() - t0)

        # tANS (Build wyciągnięty na zewnątrz)
        t0 = time.perf_counter()
        sym_of_slot, dtable_nb, dtable_base, etable = _tans_build_tables(f, cum)
        t_build = _ms(time.perf_counter() - t0)
        
        t0 = time.perf_counter()
        ts, tbytes, t_total_bits = tans_compress(data, f, etable)
        t_enc = _ms(time.perf_counter() - t0)
        t_size = max(1, (ts.bit_length() + 7) // 8) + len(tbytes) + 256
        
        t0 = time.perf_counter()
        t_dec_data = tans_decompress(ts, tbytes, t_total_bits, sym_of_slot, dtable_nb, dtable_base, orig)
        t_dec = _ms(time.perf_counter() - t0)
        t_ok = "OK" if t_dec_data == data else "ERR"

        # Zstd
        t0 = time.perf_counter()
        zcomp = cctx.compress(data)
        z_enc = _ms(time.perf_counter() - t0)
        z_size = len(zcomp)
        
        t0 = time.perf_counter()
        z_ok = "OK" if dctx.decompress(zcomp) == data else "ERR"
        z_dec = _ms(time.perf_counter() - t0)

        print(
            f"{fname[:col]:<{col}} | {orig:>10} | "
            f"{r_size:>8}  {r_size/orig*100:>5.2f}%  {r_enc:>7.1f}  {r_dec:>7.1f} | "
            f"{t_size:>8}  {t_size/orig*100:>5.2f}%  {t_build:>6.1f}  {t_enc:>7.1f}  {t_dec:>7.1f} | "
            f"{z_size:>8}  {z_size/orig*100:>5.2f}%  {z_enc:>7.1f}  {z_dec:>7.1f}"
        )
        sys.stdout.flush()

        for k, enc, dec in (("r", r_enc, r_dec), ("t", t_enc, t_dec), ("z", z_enc, z_dec)):
            totals[k][0] += enc
            totals[k][1] += dec
        file_count += 1

    print(sep)
    n = file_count or 1
    r_enc_avg, r_dec_avg = totals["r"][0] / n, totals["r"][1] / n
    t_enc_avg, t_dec_avg = totals["t"][0] / n, totals["t"][1] / n
    z_enc_avg, z_dec_avg = totals["z"][0] / n, totals["z"][1] / n
    
    print(
        f"{'AVG':^{col}} | {'':>10} | "
        f"{'':>8}  {'':>6}   {r_enc_avg:>7.1f}  {r_dec_avg:>7.1f} | "
        f"{'':>8}  {'':>6}   {'':>6}  {t_enc_avg:>7.1f}  {t_dec_avg:>7.1f} | "
        f"{'':>8}  {'':>6}   {z_enc_avg:>7.1f}  {z_dec_avg:>7.1f}"
    )

if __name__ == "__main__":
    run_comparison("./silesia")