import collections
import os
import time

# ── Shared frequency model (same scaling as rans.py) ─────────────────────────

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


# ── rANS: byte-level renormalization (from rans.py) ──────────────────────────

def rans_compress(data, f, cum, m_bits=12):
    M = 1 << m_bits
    L = 1 << 16
    state = L
    stream = []
    for byte in data:
        freq = f[byte]
        limit = (L // M) * freq * 256
        while state >= limit:
            stream.append(state & 0xFF)
            state >>= 8
        state = (state // freq) * M + (state % freq) + cum[byte]
    return state, stream

def rans_decompress(state, stream, f, cum, length, m_bits=12):
    M = 1 << m_bits
    L = 1 << 16
    lookup = [0] * M
    for s in range(256):
        for i in range(cum[s], cum[s+1]):
            lookup[i] = s
    decoded = bytearray()
    ptr = len(stream) - 1
    for _ in range(length):
        slot = state % M
        s = lookup[slot]
        decoded.append(s)
        state = f[s] * (state // M) + (slot - cum[s])
        while state < L and ptr >= 0:
            state = (state << 8) | stream[ptr]
            ptr -= 1
    return bytes(decoded[::-1])


# ── uANS: bit-level renormalization ──────────────────────────────────────────
#
# Uses the same ANS formula as rANS but renormalises one bit at a time.
# State is kept in [M, 2M) by emitting/consuming individual bits.
# Compression should be slightly tighter than byte renorm since we never
# waste up to 7 bits of alignment per renorm step.

def uans_compress(data, f, cum, m_bits=12):
    M = 1 << m_bits
    state = M
    bits = []
    for byte in data:
        freq = f[byte]
        x = state
        # renorm: shift x into [freq, 2*freq) emitting LSBs
        while x >= 2 * freq:
            bits.append(x & 1)
            x >>= 1
        # ANS step (x // freq == 1 here, so: M + cum + offset)
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
        # recover pre-renorm state: x is the renormed value the encoder had
        x = f[s] + (slot - cum[s])
        # nb bits were emitted to reach x from the original state
        nb = (m_bits + 1) - x.bit_length()
        bits_val = 0
        for i in range(nb - 1, -1, -1):
            if ptr >= 0:
                bits_val |= bits[ptr] << i
                ptr -= 1
        state = (x << nb) | bits_val
    return bytes(decoded[::-1])


# ── tANS: table ANS with precomputed decode/encode tables ────────────────────
#
# Uses sequential spread (symbol s occupies slots cum[s]..cum[s+1]-1).
# Decode table maps slot -> (symbol, nb_bits, new_state_base) avoiding
# all arithmetic in the hot loop. Encode table maps (s, x_renorm) -> new_state.

def _tans_build_tables(f, cum, m_bits=12):
    M = 1 << m_bits

    # Duda step spread: visit all M slots in a pseudo-random order.
    # step must be coprime with M=2^k, so any odd number works.
    # 0.618*M (golden-ratio fraction) gives good symbol interleaving.
    step = int(M * 0.6180339887)
    if step % 2 == 0:
        step += 1
    sym_of_slot = [-1] * M
    pos = 0
    for s in range(256):
        for _ in range(f[s]):
            sym_of_slot[pos] = s
            pos = (pos + step) % M

    # Decode table: dtable[slot] -> (symbol, nb_bits, new_state_base)
    # next_x[s] counts up from f[s]; the k-th time symbol s appears in the
    # spread it gets pre-renorm value f[s]+k, which encodes how many bits
    # the encoder consumed to reach that slot.
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

    # Encode table: etable[s][x - f[s]] = new_state, for x in [f[s], 2*f[s]).
    # Built by inverting the decode table: the slot that has pre-renorm value x
    # for symbol s is the new state for encoding (s, x).
    etable = [None] * 256
    for s in range(256):
        if f[s] > 0:
            etable[s] = [0] * f[s]
    next_x = list(f)
    for slot in range(M):
        s = sym_of_slot[slot]
        x = next_x[s]          # same x as in decode table construction
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
    # Two-line header: method names on top, sub-columns below
    print(f"{'File':<{col}} | {'Original':>10} | "
          f"{'-- rANS (byte renorm) --':^30} | "
          f"{'-- uANS (bit renorm) ---':^30} | "
          f"{'-- tANS (Duda spread) --':^30}")
    print(f"{'':^{col}} | {'':>10} | "
          f"{'Size':>8}  {'Ratio':>6}  {'Enc ms':>7}  {'Dec ms':>7} | "
          f"{'Size':>8}  {'Ratio':>6}  {'Enc ms':>7}  {'Dec ms':>7} | "
          f"{'Size':>8}  {'Ratio':>6}  {'Enc ms':>7}  {'Dec ms':>7}")
    sep = "-" * (col + 3 + 12 + 3 + 34 + 3 + 34 + 3 + 34)
    print(sep)

    totals = {k: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0] for k in ("r", "u", "t")}
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
        f, cum = build_model(data)

        # rANS
        t0 = time.perf_counter()
        rs, rstream = rans_compress(data, f, cum)
        r_enc = _ms(time.perf_counter() - t0)
        r_size = 8 + len(rstream) + 256
        t0 = time.perf_counter()
        r_ok = "OK" if rans_decompress(rs, rstream, f, cum, orig) == data else "ERR"
        r_dec = _ms(time.perf_counter() - t0)

        # uANS
        t0 = time.perf_counter()
        us, ubits = uans_compress(data, f, cum)
        u_enc = _ms(time.perf_counter() - t0)
        u_size = 8 + (len(ubits) + 7) // 8 + 256
        t0 = time.perf_counter()
        u_ok = "OK" if uans_decompress(us, ubits, f, cum, orig) == data else "ERR"
        u_dec = _ms(time.perf_counter() - t0)

        # tANS
        t0 = time.perf_counter()
        ts, tbits = tans_compress(data, f, cum)
        t_enc = _ms(time.perf_counter() - t0)
        t_size = 8 + (len(tbits) + 7) // 8 + 256
        t0 = time.perf_counter()
        t_ok = "OK" if tans_decompress(ts, tbits, f, cum, orig) == data else "ERR"
        t_dec = _ms(time.perf_counter() - t0)

        print(
            f"{fname[:col]:<{col}} | {orig:>10} | "
            f"{r_size:>8}  {r_size/orig*100:>5.2f}%  {r_enc:>7.1f}  {r_dec:>7.1f} | "
            f"{u_size:>8}  {u_size/orig*100:>5.2f}%  {u_enc:>7.1f}  {u_dec:>7.1f} | "
            f"{t_size:>8}  {t_size/orig*100:>5.2f}%  {t_enc:>7.1f}  {t_dec:>7.1f}"
        )

        for vals, enc, dec in (
            (totals["r"], r_enc, r_dec),
            (totals["u"], u_enc, u_dec),
            (totals["t"], t_enc, t_dec),
        ):
            vals[0] += r_size; vals[1] += u_size; vals[2] += t_size
            vals[3] += enc;    vals[4] += dec

        totals["r"][3] += r_enc; totals["r"][4] += r_dec
        totals["u"][3] += u_enc; totals["u"][4] += u_dec
        totals["t"][3] += t_enc; totals["t"][4] += t_dec
        file_count += 1

    # Averages
    print(sep)
    n = file_count or 1
    r_enc_avg = totals["r"][3] / n
    r_dec_avg = totals["r"][4] / n
    u_enc_avg = totals["u"][3] / n
    u_dec_avg = totals["u"][4] / n
    t_enc_avg = totals["t"][3] / n
    t_dec_avg = totals["t"][4] / n
    print(
        f"{'AVG':^{col}} | {'':>10} | "
        f"{'':>8}  {'':>6}   {r_enc_avg:>7.1f}  {r_dec_avg:>7.1f} | "
        f"{'':>8}  {'':>6}   {u_enc_avg:>7.1f}  {u_dec_avg:>7.1f} | "
        f"{'':>8}  {'':>6}   {t_enc_avg:>7.1f}  {t_dec_avg:>7.1f}"
    )
    print()
    print("Note: rANS uses byte-level renorm; uANS/tANS use bit-level renorm.")
    print("      tANS uses Duda step spread (golden-ratio interleaving).")


run_comparison("./silesia")
