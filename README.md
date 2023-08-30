# xdrip-visualizer
Python script which generates a HTML page from an exported xDrip database file.
Example output:
![image](https://github.com/palmarci/xdrip-visualizer/assets/20556689/f0c2ad50-c062-4963-8c34-df5bc3a751f0)

```
usage: xdrip-visualizer.py [-h] [--last-days LAST_DAYS] [--min-long-insulin MIN_LONG_INSULIN] [--max-long-insulin MAX_LONG_INSULIN] [--min-acceptable-bg MIN_ACCEPTABLE_BG]
                           [--max-acceptable-bg MAX_ACCEPTABLE_BG] [--no-widescreen]
                           zip_file

xDrip Database Visualizer

positional arguments:
  zip_file              ZIP file containing the xDrip database (exported from the app)

options:
  -h, --help            show this help message and exit
  --last-days LAST_DAYS
                        Number of last days to create graphs for (default: 30)
  --min-long-insulin MIN_LONG_INSULIN
                        Minimum value for long insulin (default: 12)
  --max-long-insulin MAX_LONG_INSULIN
                        Maximum value for long insulin (default: 20)
  --min-acceptable-bg MIN_ACCEPTABLE_BG
                        Minimum acceptable blood sugar value (default: 4)
  --max-acceptable-bg MAX_ACCEPTABLE_BG
                        Maximum acceptable blood sugar value (default: 12)
  --no-widescreen       Dont generate widescreen graphs

```

