import os
import io

import functions_framework
import pandas as pd
import yaml

from helper import load_files, move_csv_file, move_csv_file_gcp, insert_into_duckdb, upsert_into_bigquery, get_project_number


def process_rating_files(config, files):
    """Load rating observations without assuming the share-price date column."""
    for file in files:
        if os.getenv("K_SERVICE") and os.getenv("FUNCTION_TARGET"):
            from google.auth import default

            frame = pd.read_csv(io.StringIO(file.download_as_text()), sep="|")
            _, project_id = default()
            project_number = get_project_number(project_id)
            upsert_into_bigquery(
                frame,
                project_id,
                "stocks",
                "ratings",
                ["symbol", "source_revision_id"],
                update_matched=False,
            )
            move_csv_file_gcp(f"data-{project_number}", f"archive-{project_number}", file.name)
        else:
            frame = pd.read_csv(file, sep="|")
            insert_into_duckdb(frame, config["duckdb"]["database"], "ratings")
            move_csv_file(config["csv_directory"], config["archive"], file)


@functions_framework.http
def entry_point(request=None):
    """Load all dated rating observations without deleting older history."""
    with open("config.yml", "r") as file:
        config = yaml.safe_load(file)

    asset = "ratings"
    process_rating_files(config, load_files(config, asset))
    return "Data insertion successfully completed !\n"


if os.getenv("K_SERVICE") and os.getenv("FUNCTION_TARGET"):
    pass
else:
    print(entry_point())
