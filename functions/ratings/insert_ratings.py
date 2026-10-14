import io

import functions_framework
import pandas as pd

from helper import get_project_number, move_csv_file_gcp, upsert_into_bigquery


def process_rating_files(_config, files):
    """Load rating observations without assuming the share-price date column."""
    from google.auth import default

    _, project_id = default()
    if not project_id:
        raise RuntimeError("cloud ingestion requires an application-default project")
    project_number = get_project_number(project_id)
    for file in files:
        frame = pd.read_csv(io.StringIO(file.download_as_text()), sep="|")
        upsert_into_bigquery(
            frame,
            project_id,
            "stocks",
            "ratings",
            ["symbol", "source_revision_id"],
            update_matched=False,
        )
        move_csv_file_gcp(f"data-{project_number}", f"archive-{project_number}", file.name)


@functions_framework.http
def entry_point(request=None):
    """Load all dated rating observations without deleting older history."""
    asset = "ratings"
    from helper import load_files

    process_rating_files(None, load_files(None, asset))
    return "Data insertion successfully completed !\n"


if __name__ == "__main__":
    print(entry_point())
