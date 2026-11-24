# SQLite prefix sum benchmark

Sole author: OpenAI Codex

Stored prefix sums and a covering index were tested on the same SQLite date-range report using 5,000 NYC taxi trips. Both returned identical totals. In memory, median query time was **2.5 Âµs with prefix sums** and **220.8 Âµs with the covering index**. Prefix sums added **0.73 ms** to the initial load and broke even on the fourth execution of the same query. [Dataset](https://data.cityofnewyork.us/Transportation/2023-Yellow-Taxi-Trip-Data/4b4i-vvec) Â· [Prior work](https://doi.org/10.1145/253260.253274)

Rerun with `python taxi_one_file_demo.py` (Python 3.11 and `curl`).
