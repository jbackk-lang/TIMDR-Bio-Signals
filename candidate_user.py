import numpy as np
class TIMDRBio:
    def __init__(self, mad_scale=1.4826):
        self.mad_scale = mad_scale
    def _mad_z(self, x):
        x = np.asarray(x, float)
        if x.size == 0:
            return np.zeros_like(x)
        med = np.median(x)
        mad = np.median(np.abs(x - med)) * self.mad_scale
        if mad == 0:
            span = np.max(x) - np.min(x)
            if span == 0:
                return np.zeros_like(x)
            return (x - med) / (span / 4.0)
        return (x - med) / mad
    def twist(self, t, x, z_thresh=3.5):
        t = np.asarray(t, float)
        x = np.asarray(x, float)
        if len(t) < 3:
            return np.array([], int), np.zeros_like(x)
        dx  = np.gradient(x, t)
        ddx = np.gradient(dx, t)
        z = np.abs(self._mad_z(ddx))
        idx = np.where(z > z_thresh)[0]
        return idx, z
    def trend(self, t, x, window=200, z_thresh=3.0):
        t = np.asarray(t, float)
        x = np.asarray(x, float)
        n = len(t)
        if n < 3:
            return np.zeros_like(x), np.zeros_like(x)
        tc = t - t.mean()
        slopes = np.zeros_like(x)
        for i in range(n):
            j0 = max(0, i - window + 1)
            tt = tc[j0:i+1]
            xx = x[j0:i+1]
            A = np.column_stack([tt, np.ones_like(tt)])
            a, b = np.linalg.lstsq(A, xx, rcond=None)[0]
            slopes[i] = a
        z = np.abs(self._mad_z(slopes))
        return slopes, z
    def anomalies(self, x, z_thresh=3.0):
        x = np.asarray(x, float)
        z = np.abs(self._mad_z(x))
        idx = np.where(z > z_thresh)[0]
        return idx, z
    def rhythm(self, x, max_lag, power_thresh=0.4):
        x = np.asarray(x, float)
        n = len(x)
        if n < 4:
            return [], 0.0
        trend = np.linspace(x[0], x[-1], n)
        x_d = x - trend
        x_d = x_d - np.mean(x_d)
        ac = np.zeros(max_lag + 1)
        for lag in range(max_lag + 1):
            if lag == 0:
                ac[lag] = np.dot(x_d, x_d) / n
            else:
                overlap = n - lag
                if overlap <= 0:
                    break
                ac[lag] = np.dot(x_d[:-lag], x_d[lag:]) / overlap
        if ac[0] == 0:
            return [], 0.0
        ac /= ac[0]
        lags = np.arange(1, len(ac))
        power = ac[1:]
        dom = np.where(power >= power_thresh)[0]
        if dom.size == 0:
            return [], 0.0
        return lags[dom].tolist(), float(power[dom].max())
