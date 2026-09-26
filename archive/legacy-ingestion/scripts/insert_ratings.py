import os

import functions_framework
import yaml

from helper import load_files, process_files


@functions_framework.http
def entry_point(request=None):
    """Load all dated rating observations without deleting older history."""
    with open("config.yml", "r") as file:
        config = yaml.safe_load(file)

    asset = "ratings"
    csv_files = load_files(config, asset)
    process_files(config, csv_files, asset)
    return "Data insertion successfully completed !\n"


if os.getenv("K_SERVICE") and os.getenv("FUNCTION_TARGET"):
    pass
else:
    print(entry_point())
