import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from services.database import DatabaseManager


_JSON_TABLES = {
    "violations": {"date_key": "date", "score_key": "fine"},
    "incidents": {"date_key": "date", "score_key": "severity"},
    "training": {"date_key": "end_date", "score_key": None},
    "ppe": {"date_key": "issue_date", "score_key": None},
    "permits": {"date_key": "start_date", "score_key": None},
}


def _parse_date(val: Any) -> Optional[datetime]:
    if not val:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(val)[:10], fmt)
        except ValueError:
            continue
    return None


def _month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


class PredictiveModel:
    def __init__(self) -> None:
        self.db = DatabaseManager()

    def forecast(self, table: str, months: int = 3) -> Dict[str, Any]:
        config = _JSON_TABLES.get(table)
        if not config:
            return {"error": f"Unknown table: {table}"}

        records = self.db.get_json_records(table)
        date_key = config["date_key"]

        monthly_counts: Dict[str, int] = {}
        monthly_scores: Dict[str, float] = {}

        for rec in records:
            dj = rec.get("data_json", {})
            dt = _parse_date(dj.get(date_key, ""))
            if not dt:
                continue
            mk = _month_key(dt)
            monthly_counts[mk] = monthly_counts.get(mk, 0) + 1
            score_key = config.get("score_key")
            if score_key:
                score = float(dj.get(score_key, 0))
                monthly_scores[mk] = monthly_scores.get(mk, 0) + score

        sorted_months = sorted(monthly_counts.keys())
        if len(sorted_months) < 2:
            return {"error": "Недостаточно данных для прогноза (нужно ≥2 месяцев)"}

        last_month = datetime.strptime(sorted_months[-1] + "-01", "%Y-%m-%d")

        series = [monthly_counts[m] for m in sorted_months]
        trend = self._linear_trend(series)

        forecast_values = []
        for i in range(1, months + 1):
            pred_month = last_month + timedelta(days=32 * i)
            pred_mk = _month_key(pred_month)
            pred_val = max(0, round(series[-1] + trend * i))
            forecast_values.append({"month": pred_mk, "predicted": pred_val})

        return {
            "table": table,
            "current_month_count": series[-1],
            "trend": round(trend, 2),
            "direction": "up"
            if trend > 0.5
            else ("down" if trend < -0.5 else "stable"),
            "forecast": forecast_values,
            "total_records": len(records),
            "months_analyzed": len(sorted_months),
            "monthly_data": [
                {"month": m, "count": monthly_counts[m]} for m in sorted_months[-12:]
            ],
        }

    def risk_score(self) -> Dict[str, Any]:
        total_risk = 0.0
        breakdown: List[Dict[str, Any]] = []

        for table in ["violations", "incidents", "training", "ppe"]:
            fc = self.forecast(table, months=1)
            if "error" in fc:
                continue
            count = fc["current_month_count"]
            direction = fc["direction"]
            weight = {
                "violations": 0.35,
                "incidents": 0.30,
                "training": 0.20,
                "ppe": 0.15,
            }[table]
            score = count * weight
            if direction == "up":
                score *= 1.3
            total_risk += score
            breakdown.append(
                {
                    "table": table,
                    "count": count,
                    "trend": direction,
                    "contribution": round(score, 2),
                }
            )

        level = "low"
        if total_risk > 20:
            level = "high"
        elif total_risk > 10:
            level = "medium"

        return {
            "total_risk": round(total_risk, 2),
            "level": level,
            "breakdown": breakdown,
        }

    @staticmethod
    def _linear_trend(series: List[float]) -> float:
        n = len(series)
        if n < 2:
            return 0.0
        xs = list(range(n))
        mean_x = sum(xs) / n
        mean_y = sum(series) / n
        num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, series))
        den = sum((x - mean_x) ** 2 for x in xs)
        if den == 0:
            return 0.0
        return num / den
