import functions_framework

from helper import process_files, load_files
from ingestion_observability import observed_entrypoint

@functions_framework.http
@observed_entrypoint("ingestion.indices.insert")
def entry_point(request=None):
    # Load configuration from YAML file
    asset = "indices"
    process_files(None, load_files(None, asset))

    return "Data insertion successfully completed !\n"

if __name__ == "__main__":
    print(entry_point())
