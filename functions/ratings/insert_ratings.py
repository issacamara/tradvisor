import io

import functions_framework
import pandas as pd

from helper import get_project_number, move_csv_file_gcp, upsert_into_bigquery
from ingestion_observability import observed_entrypoint


def process_rating_files(configuration, files):
    """Load rating observations without assuming the share-price date column."""
    from google.auth import default

    _, project_id = default()
    if configuration is not None:
        configuration.validate_application_default_project(project_id)
        dataset = configuration.dataset
        table = configuration.table_for("ratings").rsplit(".", 1)[1]
        source_bucket = configuration.data_bucket
        archive_bucket = configuration.archive_bucket
    else:
        if not project_id:
            raise RuntimeError("cloud ingestion requires an application-default project")
        project_number = get_project_number(project_id)
        dataset = "stocks"
        table = "ratings"
        source_bucket = f"data-{project_number}"
        archive_bucket = f"archive-{project_number}"
    for file in files:
        frame = pd.read_csv(io.StringIO(file.download_as_text()), sep="|")
        upsert_into_bigquery(
            frame,
            project_id,
            dataset,
            table,
            ["symbol", "source_revision_id"],
            update_matched=False,
        )
        move_csv_file_gcp(source_bucket, archive_bucket, file.name)


@functions_framework.http
@observed_entrypoint("ingestion.ratings.insert")
def entry_point(request=None):
    """Load all dated rating observations without deleting older history."""
    asset = "ratings"
    from helper import load_files
    from ingestion_configuration import IngestionConfiguration

    configuration = IngestionConfiguration.from_environment()
    process_rating_files(configuration, load_files(configuration, asset))
    return "Data insertion successfully completed !\n"


if __name__ == "__main__":
    print(entry_point())
