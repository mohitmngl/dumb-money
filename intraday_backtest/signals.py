import numpy as np

try:
    from numba import njit, prange
    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False

from intraday_backtest.config import (
    ACCEL_S4, ACCEL_S8, ACCEL_S16,
    ACCEL_B3, ACCEL_B7, ACCEL_B15,
    ACCEL_LATEST_CANDLES
)


if HAS_NUMBA:
    @njit(cache=True, parallel=True)
    def _accel_kernel(C, T, K):
        """Flat Numba kernel — zero function calls in hot path."""
        result = np.empty(K, dtype=np.bool_)

        for k in prange(K):
            # Cumsum once
            cs0 = float(C[0, k])
            cs1 = cs0 + C[1, k]
            cs2 = cs1 + C[2, k]
            cs3 = cs2 + C[3, k]
            cs4 = cs3 + C[4, k]
            cs5 = cs4 + C[5, k]
            cs6 = cs5 + C[6, k]
            cs7 = cs6 + C[7, k]
            cs8 = cs7 + C[8, k]
            cs9 = cs8 + C[9, k]
            cs10 = cs9 + C[10, k]
            cs11 = cs10 + C[11, k]
            cs12 = cs11 + C[12, k]
            cs13 = cs12 + C[13, k]
            cs14 = cs13 + C[14, k]
            cs15 = cs14 + C[15, k]
            cs16 = cs16v = cs15 + C[16, k]
            cs17 = cs16 + C[17, k]
            cs18 = cs17 + C[18, k]
            cs19 = cs18 + C[19, k]

            # Only need A and B at indices 15..19
            # Rolling sums at index t: rs(n, t) = cs[t] - cs[t-n] (or cs[t] if t==n-1)
            # For t=15: rs(3)=cs15-cs12, rs(4)=cs15-cs11, rs(7)=cs15-cs8, rs(8)=cs15-cs7, rs(15)=cs15-cs0=cs15, rs(16)=0
            # For t=16: rs(3)=cs16-cs13, rs(4)=cs16-cs12, rs(7)=cs16-cs9, rs(8)=cs16-cs8, rs(15)=cs16-cs1, rs(16)=cs16
            # For t=17: rs(3)=cs17-cs14, rs(4)=cs17-cs13, rs(7)=cs17-cs10, rs(8)=cs17-cs9, rs(15)=cs17-cs2, rs(16)=cs17-cs1
            # For t=18: rs(3)=cs18-cs15, rs(4)=cs18-cs14, rs(7)=cs18-cs11, rs(8)=cs18-cs10, rs(15)=cs18-cs3, rs(16)=cs18-cs2
            # For t=19: rs(3)=cs19-cs16, rs(4)=cs19-cs15, rs(7)=cs19-cs12, rs(8)=cs19-cs11, rs(15)=cs19-cs4, rs(16)=cs19-cs3

            A5 = np.empty(5, dtype=np.float64)
            B5 = np.empty(5, dtype=np.float64)

            # t=15
            s4 = cs15 - cs11; s8 = cs15 - cs7; s16 = cs15
            s3 = cs15 - cs12; s7 = cs15 - cs8; s15v = cs15 - cs0
            c15 = float(C[15, k])
            denom = 8.0 * (c15 + s3) * (c15 + s3)
            A5[0] = s16 * s8 / (8.0 * s4 * s4) if abs(s4) > 1e-30 else 0.0
            B5[0] = (c15 + s15v) * (c15 + s7) / denom if abs(denom) > 1e-30 else 0.0

            # t=16
            s4 = cs16 - cs12; s8 = cs16 - cs8; s16 = cs16 - cs0
            s3 = cs16 - cs13; s7 = cs16 - cs9; s15v = cs16 - cs1
            c16 = float(C[16, k])
            denom = 8.0 * (c16 + s3) * (c16 + s3)
            A5[1] = s16 * s8 / (8.0 * s4 * s4) if abs(s4) > 1e-30 else 0.0
            B5[1] = (c16 + s15v) * (c16 + s7) / denom if abs(denom) > 1e-30 else 0.0

            # t=17
            s4 = cs17 - cs13; s8 = cs17 - cs9; s16 = cs17 - cs1
            s3 = cs17 - cs14; s7 = cs17 - cs10; s15v = cs17 - cs2
            c17 = float(C[17, k])
            denom = 8.0 * (c17 + s3) * (c17 + s3)
            A5[2] = s16 * s8 / (8.0 * s4 * s4) if abs(s4) > 1e-30 else 0.0
            B5[2] = (c17 + s15v) * (c17 + s7) / denom if abs(denom) > 1e-30 else 0.0

            # t=18
            s4 = cs18 - cs14; s8 = cs18 - cs10; s16 = cs18 - cs2
            s3 = cs18 - cs15; s7 = cs18 - cs11; s15v = cs18 - cs3
            c18 = float(C[18, k])
            denom = 8.0 * (c18 + s3) * (c18 + s3)
            A5[3] = s16 * s8 / (8.0 * s4 * s4) if abs(s4) > 1e-30 else 0.0
            B5[3] = (c18 + s15v) * (c18 + s7) / denom if abs(denom) > 1e-30 else 0.0

            # t=19
            s4 = cs19 - cs15; s8 = cs19 - cs11; s16 = cs19 - cs3
            s3 = cs19 - cs16; s7 = cs19 - cs12; s15v = cs19 - cs4
            c19 = float(C[19, k])
            denom = 8.0 * (c19 + s3) * (c19 + s3)
            A5[4] = s16 * s8 / (8.0 * s4 * s4) if abs(s4) > 1e-30 else 0.0
            B5[4] = (c19 + s15v) * (c19 + s7) / denom if abs(denom) > 1e-30 else 0.0

            # Conditions
            cond1 = C[T - 1, k] > C[T - 2, k]

            cond2 = True
            for j in range(4):
                if A5[j + 1] <= A5[j]:
                    cond2 = False
                    break

            cond3 = True
            for j in range(3):
                if B5[j + 1] <= B5[j]:
                    cond3 = False
                    break
            if B5[4] >= B5[3]:
                cond3 = False

            cond4 = True
            for j in range(5):
                if abs(A5[j]) < 1e-30:
                    cond4 = False
                    break
                bcp = 100.0 * (B5[j] / A5[j] - 1.0)
                if not (np.isfinite(bcp) and bcp > 0):
                    cond4 = False
                    break

            result[k] = cond1 and cond2 and cond3 and cond4

        return result

    def accel_peak_signal(batch_prices_latest20):
        """Accel Peak Signal with Numba JIT — ~200x faster than pure numpy."""
        C = np.ascontiguousarray(batch_prices_latest20, dtype=np.float32)
        T, K = C.shape
        return _accel_kernel(C, T, K)

else:
    def accel_peak_signal(batch_prices_latest20):
        C = np.asarray(batch_prices_latest20, dtype=np.float32)
        T, K = C.shape

        cs = np.cumsum(C, axis=0)

        def rsum(n):
            out = np.empty_like(C)
            out[:n-1] = 0.0
            out[n-1] = cs[n-1]
            out[n:] = cs[n:] - cs[:-n]
            return out

        S3 = rsum(ACCEL_B3)
        S4 = rsum(ACCEL_S4)
        S7 = rsum(ACCEL_B7)
        S8 = rsum(ACCEL_S8)
        S15 = rsum(ACCEL_B15)
        S16 = rsum(ACCEL_S16)

        S4_sq = S4 * S4
        A = S16 * S8
        A /= (8.0 * S4_sq)

        C_plus_S15 = C + S15
        C_plus_S7 = C + S7
        C_plus_S3 = C + S3
        B = C_plus_S15 * C_plus_S7
        B /= (8.0 * C_plus_S3 * C_plus_S3)

        with np.errstate(divide='ignore', invalid='ignore'):
            BCP = 100.0 * (B / A - 1.0)

        latest_ret = C[-1] / C[-2] - 1.0
        A5 = A[-5:]
        B5 = B[-5:]
        BCP5 = BCP[-5:]

        cond1 = latest_ret > 0
        cond2 = np.all(np.diff(A5, axis=0) > 0, axis=0)
        cond3 = np.all(np.diff(B5[:-1], axis=0) > 0, axis=0) & (B5[-1] < B5[-2])
        cond4 = np.all(np.isfinite(BCP5) & (BCP5 > 0), axis=0)

        return cond1 & cond2 & cond3 & cond4
