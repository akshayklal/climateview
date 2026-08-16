from pathlib import Path
from runpy import run_path


run = run_path(Path(__file__).with_name("noaa-build-processed-data.py"))["run"]


if __name__ == "__main__":
    run("precipitation")
