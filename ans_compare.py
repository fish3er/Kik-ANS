import collections
import os
import sys
import time

# ── Shared frequency model ────────────────────────────────────────────────────

def build_model(data, m_bits=12):
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


# FIX 2: rANS now uses bit-level renorm (same as uANS/tANS) so all three
# methods differ only in ANS arithmetic vs table lookup, not renorm strategy.
# ── rANS: bit-level renormalization ──────────────────────────────────────────

def rans_compress(data, f, cum, m_bits=12):
    M = 1 << m_bits
    state = M
    bits = []
    for byte in data:
        freq = f[byte]
        x = state
        # FIX 2: bit renorm replaces former byte renorm loop
        while x >= 2 * freq:
            bits.append(x & 1)
            x >>= 1
        state = (x // freq) * M + (x % freq) + cum[byte]
    return state, bits

def rans_decompress(state, bits, f, cum, length, m_bits=12):
    M = 1 << m_bits
    lookup = [0] * M
    for s in range(256):
        for i in range(cum[s], cum[s+1]):
            lookup[i] = s
    decoded = bytearray()
    ptr = len(bits) - 1
    for _ in range(length):
        # FIX 2: state always in [M, 2M) after bit renorm; slot = state - M
        slot = state - M
        s = lookup[slot]
        decoded.append(s)
        x = f[s] + (slot - cum[s])
        nb = (m_bits + 1) - x.bit_length()
        bits_val = 0
        for i in range(nb - 1, -1, -1):
            if ptr >= 0:
                bits_val |= bits[ptr] << i
                ptr -= 1
        state = (x << nb) | bits_val
    return bytes(decoded[::-1])


# ── uANS: bit-level renormalization ──────────────────────────────────────────

def uans_compress(data, f, cum, m_bits=12):
    M = 1 << m_bits
    state = M
    bits = []
    for byte in data:
        freq = f[byte]
        x = state
        while x >= 2 * freq:
            bits.append(x & 1)
            x >>= 1
        state = M + cum[byte] + (x - freq)
    return state, bits

def uans_decompress(state, bits, f, cum, length, m_bits=12):
    M = 1 << m_bits
    sym_of_slot = [0] * M
    for s in range(256):
        for i in range(cum[s], cum[s+1]):
            sym_of_slot[i] = s
    decoded = bytearray()
    ptr = len(bits) - 1
    for _ in range(length):
        slot = state - M
        s = sym_of_slot[slot]
        decoded.append(s)
        x = f[s] + (slot - cum[s])
        nb = (m_bits + 1) - x.bit_length()
        bits_val = 0
        for i in range(nb - 1, -1, -1):
            if ptr >= 0:
                bits_val |= bits[ptr] << i
                ptr -= 1
        state = (x << nb) | bits_val
    return bytes(decoded[::-1])


# ── tANS: table ANS with precomputed decode/encode tables ────────────────────

def _tans_build_tables(f, cum, m_bits=12):
    M = 1 << m_bits

    # FIX 3: sequential spread (symbol s occupies slots cum[s]..cum[s+1]-1)
    # replaces the golden-ratio step spread so the only variable vs uANS is
    # table lookup vs arithmetic in the hot loop.
    sym_of_slot = [0] * M
    for s in range(256):
        for i in range(cum[s], cum[s+1]):
            sym_of_slot[i] = s

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

def tans_compress(data, f, cum, m_bits=12):
    M = 1 << m_bits
    _, _, _, etable = _tans_build_tables(f, cum, m_bits)
    state = M
    bits = []
    for byte in data:
        freq = f[byte]
        x = state
        while x >= 2 * freq:
            bits.append(x & 1)
            x >>= 1
        state = etable[byte][x - freq]
    return state, bits

def tans_decompress(state, bits, f, cum, length, m_bits=12):
    sym_of_slot, dtable_nb, dtable_base, _ = _tans_build_tables(f, cum, m_bits)
    M = 1 << m_bits
    decoded = bytearray()
    ptr = len(bits) - 1
    for _ in range(length):
        slot = state - M
        s   = sym_of_slot[slot]
        nb  = dtable_nb[slot]
        base = dtable_base[slot]
        decoded.append(s)
        bits_val = 0
        for i in range(nb - 1, -1, -1):
            if ptr >= 0:
                bits_val |= bits[ptr] << i
                ptr -= 1
        state = base | bits_val
    return bytes(decoded[::-1])


# ── Comparison runner ─────────────────────────────────────────────────────────

def _ms(t): return t * 1000.0

def run_comparison(folder_path="./silesia"):
    if not os.path.exists(folder_path):
        print(f"Folder '{folder_path}' not found.")
        return

    col = 15
    print(f"{'File':<{col}} | {'Original':>10} | "
          f"{'-- rANS (bit renorm) ---':^30} | "
          f"{'-- uANS (bit renorm) ---':^30} | "
          f"{'-- tANS (seq spread) ---':^30}")
    print(f"{'':^{col}} | {'':>10} | "
          f"{'Size':>8}  {'Ratio':>6}  {'Enc ms':>7}  {'Dec ms':>7} | "
          f"{'Size':>8}  {'Ratio':>6}  {'Enc ms':>7}  {'Dec ms':>7} | "
          f"{'Size':>8}  {'Ratio':>6}  {'Enc ms':>7}  {'Dec ms':>7}")
    sep = "-" * (col + 3 + 12 + 3 + 34 + 3 + 34 + 3 + 34)
    print(sep)

    # FIX 1: simplified totals — only track enc/dec times per method
    totals = {k: [0.0, 0.0] for k in ("r", "u", "t")}
    file_count = 0

    for fname in sorted(os.listdir(folder_path)):
        fpath = os.path.join(folder_path, fname)
        if not os.path.isfile(fpath):
            continue
        with open(fpath, "rb") as fh:
            data = fh.read()
        if not data:
            continue

        orig = len(data)
        print(f"  {fname} ({orig / 1e6:.1f} MB) ...", end="", file=sys.stderr, flush=True)
        f, cum = build_model(data)

        # rANS
        t0 = time.perf_counter()
        rs, rbits = rans_compress(data, f, cum)
        r_enc = _ms(time.perf_counter() - t0)
        # FIX 4: variable-length final state size instead of hardcoded 8 bytes
        r_size = max(1, (rs.bit_length() + 7) // 8) + (len(rbits) + 7) // 8 + 256
        t0 = time.perf_counter()
        r_ok = "OK" if rans_decompress(rs, rbits, f, cum, orig) == data else "ERR"
        r_dec = _ms(time.perf_counter() - t0)

        # uANS
        t0 = time.perf_counter()
        us, ubits = uans_compress(data, f, cum)
        u_enc = _ms(time.perf_counter() - t0)
        # FIX 4: variable-length final state size
        u_size = max(1, (us.bit_length() + 7) // 8) + (len(ubits) + 7) // 8 + 256
        t0 = time.perf_counter()
        u_ok = "OK" if uans_decompress(us, ubits, f, cum, orig) == data else "ERR"
        u_dec = _ms(time.perf_counter() - t0)

        # tANS
        t0 = time.perf_counter()
        ts, tbits = tans_compress(data, f, cum)
        t_enc = _ms(time.perf_counter() - t0)
        # FIX 4: variable-length final state size
        t_size = max(1, (ts.bit_length() + 7) // 8) + (len(tbits) + 7) // 8 + 256
        t0 = time.perf_counter()
        t_ok = "OK" if tans_decompress(ts, tbits, f, cum, orig) == data else "ERR"
        t_dec = _ms(time.perf_counter() - t0)

        total_enc_ms = r_enc + u_enc + t_enc
        print(f" {total_enc_ms / 1000:.1f}s", file=sys.stderr)
        if total_enc_ms > 30_000:
            print(f"  WARNING: {fname} encoding took {total_enc_ms:.0f} ms (>{30_000} ms threshold)",
                  file=sys.stderr)

        print(
            f"{fname[:col]:<{col}} | {orig:>10} | "
            f"{r_size:>8}  {r_size/orig*100:>5.2f}%  {r_enc:>7.1f}  {r_dec:>7.1f} | "
            f"{u_size:>8}  {u_size/orig*100:>5.2f}%  {u_enc:>7.1f}  {u_dec:>7.1f} | "
            f"{t_size:>8}  {t_size/orig*100:>5.2f}%  {t_enc:>7.1f}  {t_dec:>7.1f}"
        )
        sys.stdout.flush()

        # FIX 1: single accumulation pass, no duplicate block after loop
        for k, enc, dec in (("r", r_enc, r_dec), ("u", u_enc, u_dec), ("t", t_enc, t_dec)):
            totals[k][0] += enc
            totals[k][1] += dec
        file_count += 1

    print(sep)
    n = file_count or 1
    # FIX 1: index into simplified [enc, dec] totals
    r_enc_avg, r_dec_avg = totals["r"][0] / n, totals["r"][1] / n
    u_enc_avg, u_dec_avg = totals["u"][0] / n, totals["u"][1] / n
    t_enc_avg, t_dec_avg = totals["t"][0] / n, totals["t"][1] / n
    print(
        f"{'AVG':^{col}} | {'':>10} | "
        f"{'':>8}  {'':>6}   {r_enc_avg:>7.1f}  {r_dec_avg:>7.1f} | "
        f"{'':>8}  {'':>6}   {u_enc_avg:>7.1f}  {u_dec_avg:>7.1f} | "
        f"{'':>8}  {'':>6}   {t_enc_avg:>7.1f}  {t_dec_avg:>7.1f}"
    )
    print()
    print("All three methods use bit-level renorm.")
    print("rANS: division-based ANS step. uANS: simplified step (x in [freq,2freq)).")
    print("tANS: precomputed encode/decode tables, sequential slot spread.")


run_comparison("./silesia")
