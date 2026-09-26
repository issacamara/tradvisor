# Store Adapter Selection

`FirestoreRestStore` is the dependency-free adapter for local emulator-style
tests. It requires `FIRESTORE_EMULATOR_HOST` or an explicit local host and does
not create credentials.

Production application composition should install the `backend[firestore]`
extra and construct `FirestoreSdkStore(project_id=..., database_id=...)`.
When no client is injected, it creates the authenticated Google Cloud Python
server SDK client using Application Default Credentials. Tests in this ticket
do not contact Google Cloud and do not provision or apply indexes.
