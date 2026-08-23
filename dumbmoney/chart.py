import math
import json


class CandleChart:
    """Vanilla SVG candlestick chart with SuperTrend overlay and Accel sub-pane."""

    def __init__(self, width=900, height=500):
        self.width = width
        self.height = height
        self.padding = {"top": 20, "right": 60, "bottom": 80, "left": 20}
        self.candle_width = 8
        self.gap = 2
        self.colors = {
            "up": "#10b981", "down": "#ef4444", "bg": "#ffffff",
            "grid": "#e5e7eb", "text": "#6b7280", "border": "#d1d5db",
            "st_up": "#10b981", "st_down": "#ef4444",
            "accel_a": "#3b82f6", "accel_base": "#ef4444",
            "volume_up": "rgba(16,185,129,0.3)", "volume_down": "rgba(239,68,68,0.3)"
        }

    def render(self, ohlc_data, supertrend_data=None, accel_data=None, title=""):
        """Render SVG string from OHLC data + optional overlays.
        ohlc_data: list of {date, open, high, low, close, volume}
        supertrend_data: list of {date, supertrend, trend}
        accel_data: list of {date, accel_a, accel_base}"""
        if not ohlc_data:
            return self._empty_svg(title)

        n = len(ohlc_data)
        chart_w = self.width - self.padding["left"] - self.padding["right"]
        main_h = self.height - self.padding["top"] - self.padding["bottom"]
        accel_h = int(main_h * 0.25) if accel_data else 0
        price_h = main_h - accel_h - (10 if accel_data else 0)

        all_highs = [d["high"] for d in ohlc_data]
        all_lows = [d["low"] for d in ohlc_data]
        if supertrend_data:
            st_vals = [d["supertrend"] for d in supertrend_data if d.get("supertrend") is not None]
            all_highs.extend(st_vals)
            all_lows.extend(st_vals)

        price_max = max(all_highs) if all_highs else 100
        price_min = min(all_lows) if all_lows else 0
        price_range = price_max - price_min if price_max != price_min else 1
        price_max += price_range * 0.05
        price_min -= price_range * 0.05
        price_range = price_max - price_min

        volumes = [d.get("volume", 0) for d in ohlc_data]
        vol_max = max(volumes) if volumes else 1

        bar_total = chart_w / n if n > 0 else 10
        candle_w = max(1, bar_total - self.gap)

        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
            f'width="{self.width}" height="{self.height}" style="font-family:system-ui,sans-serif;background:{self.colors["bg"]}">'
        ]

        svg_parts.append(f'<defs><clipPath id="chart-clip"><rect x="{self.padding["left"]}" y="{self.padding["top"]}" '
                        f'width="{chart_w}" height="{price_h}"/></clipPath></defs>')

        for i in range(5):
            y = self.padding["top"] + (price_h * i / 4)
            val = price_max - (price_range * i / 4)
            svg_parts.append(f'<line x1="{self.padding["left"]}" y1="{y}" x2="{self.width - self.padding["right"]}" y2="{y}" '
                           f'stroke="{self.colors["grid"]}" stroke-width="0.5"/>')
            svg_parts.append(f'<text x="{self.width - self.padding["right"] + 5}" y="{y + 4}" '
                           f'fill="{self.colors["text"]}" font-size="10">{val:.2f}</text>')

        vol_h = price_h * 0.15
        vol_top = self.padding["top"] + price_h - vol_h

        for i, bar in enumerate(ohlc_data):
            x = self.padding["left"] + i * bar_total + self.gap / 2
            o, h, l, c = bar["open"], bar["high"], bar["low"], bar["close"]
            is_up = c >= o

            color = self.colors["up"] if is_up else self.colors["down"]

            def _y(price):
                return self.padding["top"] + (price_max - price) / price_range * price_h

            wick_x = x + candle_w / 2
            svg_parts.append(f'<line x1="{wick_x}" y1="{_y(h)}" x2="{wick_x}" y2="{_y(l)}" '
                           f'stroke="{color}" stroke-width="1"/>')

            body_top = _y(max(o, c))
            body_bot = _y(min(o, c))
            body_h = max(1, body_bot - body_top)
            svg_parts.append(f'<rect x="{x}" y="{body_top}" width="{candle_w}" height="{body_h}" '
                           f'fill="{color}" rx="1"/>')

            vol = bar.get("volume", 0)
            vol_bar_h = (vol / vol_max * vol_h) if vol_max > 0 else 0
            vol_color = self.colors["volume_up"] if is_up else self.colors["volume_down"]
            svg_parts.append(f'<rect x="{x}" y="{vol_top + vol_h - vol_bar_h}" width="{candle_w}" '
                           f'height="{vol_bar_h}" fill="{vol_color}"/>')

        if supertrend_data:
            st_map = {d["date"]: d for d in supertrend_data}
            prev_x = None
            prev_y = None
            prev_trend = None
            for i, bar in enumerate(ohlc_data):
                date = bar["date"]
                if date in st_map:
                    st = st_map[date]
                    st_val = st.get("supertrend")
                    trend = st.get("trend", 0)
                    if st_val is not None:
                        x = self.padding["left"] + i * bar_total + candle_w / 2
                        y = _y(st_val)
                        if prev_x is not None:
                            color = self.colors["st_up"] if trend == 1 else self.colors["st_down"]
                            svg_parts.append(f'<line x1="{prev_x}" y1="{prev_y}" x2="{x}" y2="{y}" '
                                           f'stroke="{color}" stroke-width="2"/>')
                        prev_x, prev_y, prev_trend = x, y, trend

            for i, bar in enumerate(ohlc_data):
                date = bar["date"]
                if date in st_map:
                    st = st_map[date]
                    if st.get("signal", 0) != 0:
                        x = self.padding["left"] + i * bar_total + candle_w / 2
                        is_cross_up = st["signal"] == 1
                        cy = _y(st["supertrend"]) + (-10 if is_cross_up else 10)
                        color = self.colors["up"] if is_cross_up else self.colors["down"]
                        arrow = "&#9650;" if is_cross_up else "&#9660;"
                        svg_parts.append(f'<text x="{x}" y="{cy}" text-anchor="middle" '
                                       f'fill="{color}" font-size="10">{arrow}</text>')

        if accel_data:
            accel_top = self.padding["top"] + price_h + 10
            accel_vals_a = [d.get("accel_a", 0) for d in accel_data if d.get("accel_a") is not None]
            accel_vals_b = [d.get("accel_base", 0) for d in accel_data if d.get("accel_base") is not None]
            all_accel = accel_vals_a + accel_vals_b
            if all_accel:
                a_max = max(all_accel) if all_accel else 1
                a_min = min(all_accel) if all_accel else 0
                a_range = a_max - a_min if a_max != a_min else 1

                svg_parts.append(f'<rect x="{self.padding["left"]}" y="{accel_top}" '
                               f'width="{chart_w}" height="{accel_h}" fill="#f9fafb" rx="4"/>')
                svg_parts.append(f'<text x="{self.padding["left"] + 5}" y="{accel_top + 12}" '
                               f'fill="{self.colors["text"]}" font-size="9">Accel</text>')

                prev_ax = None
                prev_ay = None
                prev_bx = None
                prev_by = None
                for i, ad in enumerate(accel_data):
                    x = self.padding["left"] + i * bar_total + candle_w / 2
                    a_val = ad.get("accel_a")
                    b_val = ad.get("accel_base")
                    if a_val is not None:
                        ay = accel_top + accel_h - (a_val - a_min) / a_range * accel_h
                        if prev_ax is not None:
                            svg_parts.append(f'<line x1="{prev_ax}" y1="{prev_ay}" x2="{x}" y2="{ay}" '
                                           f'stroke="{self.colors["accel_a"]}" stroke-width="1.5"/>')
                        prev_ax, prev_ay = x, ay
                    if b_val is not None:
                        by = accel_top + accel_h - (b_val - a_min) / a_range * accel_h
                        if prev_bx is not None:
                            svg_parts.append(f'<line x1="{prev_bx}" y1="{prev_by}" x2="{x}" y2="{by}" '
                                           f'stroke="{self.colors["accel_base"]}" stroke-width="1.5"/>')
                        prev_bx, prev_by = x, by

                    cross_up = ad.get("accel_crossed_up", 0)
                    cross_down = ad.get("accel_crossed_down", 0)
                    if (cross_up or cross_down) and a_val is not None:
                        ay = accel_top + accel_h - (a_val - a_min) / a_range * accel_h
                        color = self.colors["up"] if cross_up else self.colors["down"]
                        svg_parts.append(f'<circle cx="{x}" cy="{ay}" r="3" fill="{color}"/>')

        label_step = max(1, n // 8)
        for i in range(0, n, label_step):
            bar = ohlc_data[i]
            x = self.padding["left"] + i * bar_total + candle_w / 2
            date_label = bar["date"][-5:] if len(bar["date"]) >= 5 else bar["date"]
            svg_parts.append(f'<text x="{x}" y="{self.height - 5}" text-anchor="middle" '
                           f'fill="{self.colors["text"]}" font-size="9" transform="rotate(-30,{x},{self.height - 5})">{date_label}</text>')

        if title:
            svg_parts.append(f'<text x="{self.width / 2}" y="15" text-anchor="middle" '
                           f'fill="#0f1f17" font-size="13" font-weight="600">{title}</text>')

        svg_parts.append(f'<text x="{self.padding["left"]}" y="{self.height - 5}" '
                       f'fill="{self.colors["text"]}" font-size="9">{n} bars</text>')

        svg_parts.append('</svg>')
        return "\n".join(svg_parts)

    def _empty_svg(self, title=""):
        return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}"
            width="{self.width}" height="{self.height}" style="font-family:system-ui,sans-serif;background:#f9fafb">
            <text x="{self.width/2}" y="{self.height/2}" text-anchor="middle" fill="#6b7280" font-size="14">
                {title or "No data available"}</text></svg>'''
