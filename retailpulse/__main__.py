"""Run everything in order: Superstore pipeline -> statistics -> forecast -> discount scenarios -> UCI ingestion
(catch up) -> daily forecast -> anomalies -> snapshots -> Tableau extracts -> insights -> Tableau docs + starter
workbook -> weekly report."""
import json
import logging

from . import (analysis, anomalies, extracts, forecast, forecast_daily, ingest, insights, pipeline, report, scenarios,
               snapshot, tableau)

UCI_LAST_DAY = "2011-12-09"     # the dataset ends here; ingest catches up to it

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    report_ = pipeline.run()
    analysis.run()
    forecast.run()
    scenarios.run()
    ingest.run(through=UCI_LAST_DAY)
    forecast_daily.run()
    anomalies.run()
    snapshots = snapshot.run()
    counts = extracts.run()
    insights.run()
    tableau.run()
    print(json.dumps({"mart_counts": report_["mart_counts"], "snapshots": snapshots, "tableau_extracts": counts,
                      "weekly_report": str(report.run())}, indent=2))
