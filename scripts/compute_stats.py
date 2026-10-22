import pandas as pd
import pathlib
import io 

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

    print(dates)
    
    # data structure
    data = {}
    for name in names:
        data[name] = {}
        for date in dates:
            data[name][date] = {}
            for time in times:
                data[name][date][time] = {"readings": {}, "summary": {}}

    root = pathlib.Path('./../data')
    csv_dirs = [
        root / pathlib.Path(date)
        for date in dates
    ]

    for dir in csv_dirs:

        # csv is a file object        
        for csv in dir.iterdir():

            # parse it and store it
            _, name, time, date = csv.stem.split('_') 
            fpath = str(csv.absolute())

            with open(fpath) as f:
                lines = f.readlines()

                metadata, readings = lines[:8], lines[9:]

                # constructing the df of readings data
                readings_headers = [h.strip() for h in readings[0].split(',')]
                data[name][date][time]['readings'] = pd.read_csv(
                    io.StringIO("".join(readings)), 
                    header=None, 
                    names=readings_headers
                )

                print(dict(
                    line.split(': ', 1) for line in metadata
                ))

                # assigning the summary statistics
                data[name][date][time]["summary"] = dict(
                    line.strip().split(": ", 1) for line in metadata if ": " in line
                )
    
    return data

def compute_location_variance(location, dataset: dict):

    if location not in dataset.keys(): raise ValueError()

    values = [
        float(time["summary"]["Avg (dBA)"])
        for date in dataset[location].values()
        for time in date.values()
        if time["summary"] and "Avg (dBA)" in time["summary"]
    ]

    average = sum(values) / len(values)
    square_diffs = [
        (val - average)**2
        for val in values
    ]

    return sum(square_diffs) / (len(values) - 1)

if __name__ == "__main__":

    data = make_dataset()
    locations = ['atrium', 'cafeteria', 'study']
    for l in locations:
        print(l)
        
        var = compute_location_variance(l, data)
        print(f'Variance: {var}')