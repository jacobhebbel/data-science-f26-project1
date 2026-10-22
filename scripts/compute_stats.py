import pandas as pd
import pathlib
import re 

def make_dataset():

    # going to organize the data into this structure
    # data -> name -> date -> time -> { readings, summary }


    # The data is organized like this:
    # /data
    # -> /date
    # -> -> floor_name_time_date.csv

    days = range(5, 10)
    dates = [f'10-0{str(day)}-26' for day in days]
    names = ['atrium', 'cafeteria', 'study']
    times = ['10am', '11am', '12pm', '1pm', '2pm', '3pm', '4pm', '5pm']
    
    # data structure
    data = {
        name: {
            date: {
                time: {
                    'readings': None,
                    'summary': None
                }
            }
        }

        for time in times
        for date in dates 
        for name in names
    }

    root = pathlib.Path('csvs')
    csv_dirs = [
        root / pathlib.Path(date)
        for date in dates
    ]

    for dir in csv_dirs:
        csvs = dir.iterdir()

        # csv is a file object        
        for csv in csvs:

            # parse it and store it
            _, name, time, date = csv.name.split('_') 
            fpath = str(csv.absolute)

            with open(fpath) as f:
                lines = f.readlines()

                metadata, readings = lines[:8], lines[9:]

                # name, date, time

                readings_headers = readings[0].split(',')
                readings_data = readings[1:]
                data[name][date][time]['readings'] = 