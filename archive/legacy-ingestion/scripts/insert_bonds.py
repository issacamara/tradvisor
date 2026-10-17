import functions_framework
from helper import load_files, process_files
from ingestion_observability import observed_entrypoint


@functions_framework.http
@observed_entrypoint("ingestion.bonds.insert")
def entry_point(request=None):
    asset = "bonds"
    process_files(None, load_files(None, asset))

    return "Data insertion successfully completed !\n"

if __name__ == "__main__":
    entry_point()
