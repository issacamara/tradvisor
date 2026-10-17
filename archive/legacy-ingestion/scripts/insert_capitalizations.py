import functions_framework
from helper import process_files, load_files
from ingestion_observability import observed_entrypoint

@functions_framework.http
@observed_entrypoint("ingestion.capitalizations.insert")
def entry_point(request=None):
    asset = "capitalizations"
    process_files(None, load_files(None, asset))

    return "Data insertion successfully completed !\n"

if __name__ == "__main__":
    entry_point()
