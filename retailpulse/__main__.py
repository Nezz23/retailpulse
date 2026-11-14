"""Run everything in order: pipeline -> statistics -> forecast -> Tableau extracts -> insights -> Tableau docs + starter workbook."""
import json
import logging

from . import analysis, extracts, forecast, insights, pipeline, tableau

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    report = pipeline.run()
    analysis.run()
    forecast.run()
    counts = extracts.run()
    insights.run()
    tableau.run()
    print(json.dumps({"mart_counts": report["mart_counts"], "tableau_extracts": counts}, indent=2))
