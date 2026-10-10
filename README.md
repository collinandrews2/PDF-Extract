# PDF-Extract

This will be able to pull financial data and map it from scanned or Born-digital PDFs

Our system will follow a normal ETL pipeline. This system will go generally as follows:

1. Clients will organize and send in papers into preordained buckets via our collaboration tools.
2. We will have these buckets stored and prepared for client data ingestion when called upon by the assigned accountant.
3. Once accountant calls for information import (our trigger event) we will test the pdf docs for readability.
4. PDFs will either be determined as born digital or scanned (other items like excel will be mapped to import or saved normally)
5. PDFs will either be data extracted using text extract, OCR methods, or both
6. Data cleaning will occur with the accountant to ensure errors are handled (Licensed AI will assist with this)
7. A data load will occur in our native file database or archive and plugged directly into the tax software where possible.

Client Collaboration:
Our most important step will occur before data is given to us. This will be at the client side organization. Clients use information provided
by our collaboration tools to cleanly organize to the best of their abilities their data and paperwork before we organize it further. This
process will help us keep common type files such as W-2s from less common types such as complex investment or equity data.
