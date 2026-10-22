from matplotlib import pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import pathlib
import io

def load_csv(path):
    # reads the file with standard input then attaches metadata fields

    # Start Time
    # Export Time
    # Min
    # Max
    # Peak
    # Avg
    # TWA
    # Dose

    with open(path, 'r') as f:
        lines = f.readlines()
        metadata, headers, recordings = lines[:8], lines[9], lines[10:]
        headers = [h.strip() for h in headers.split(",")]

        # handle recording data first
        csv_data = "".join(recordings)
        df = pd.read_csv(io.StringIO(csv_data), header=None, names=headers)

        # build formatted metadata headers
        meta_map = {}
        for line in metadata:

            # parsing data
            key, val = line.split(':', maxsplit=1)
            key = key.split(' ', maxsplit=1)[0].lower()
            
            # saving result
            meta_map.update({key.strip(): val.strip()})
        
        for k,v in meta_map.items(): df.attrs[k] = v

        print(df.attrs)

        return df

def get_data() -> dict:

    # parses all csvs into one filename-dataframe map

    pfx = 'data/'
    dirs = [ pathlib.Path(pfx + f'10-0{x}-26') for x in range(5,10) ]
    csvs = [ csv for dir in dirs for csv in dir.iterdir() ]
    data = { csv.name: load_csv(csv.resolve()) for csv in csvs }
    return data

def make_location_linecharts(data: dict[str,pd.DataFrame]):

    locations = [ 'atrium', 'cafeteria', 'study' ]
    locational_datasets = {
        loc: {
            k: v for k,v in data.items()
            if loc in k
        } for loc in locations
    }

    for loc in locations:
        dataset = locational_datasets[loc]
        labels = { 
            '10-05-26': 'monday',
            '10-06-26': 'tuesday',
            '10-07-26': 'wednesday',
            '10-08-26': 'thursday',
            '10-09-26': 'friday'
        }

        fnames = [d for d in dataset.keys()]
        print(len(fnames))
        # organizes data by day, used to 
        averages_by_day = {
            day: {
                v.attrs['start']:v.attrs['avg'] for k,v in dataset.items()
                if date in k
            } for date, day in labels.items()
        }

        # line chart plot looks like:
        # time (hours from 10am to 5pm) axis (independent)
        # dBA recording axis (dependent)
        # samples are colored by their day bucket
        # legend maps colors to keys

        fig, ax = plt.subplots(figsize=(10, 6))

        median_vals = [[] for _ in range(8)]
        ax.set_ylim(45.0, 80.0)
        for day, averages in averages_by_day.items():

            # if day.upper() == 'monday'.upper(): continue

            # list(dict) makes (k, v) tuples. sorting on [0] compares start times in ascending order
            sorted_averages = sorted(list(averages.items()), key=lambda x: x[0])
            x_vals = [pd.to_datetime(avg[0].split(' ', maxsplit=1)[-1]) for avg in sorted_averages]
            y_vals = [float(avg[1]) for avg in sorted_averages]

            # plot data
            ax.plot(x_vals, y_vals, marker='o', linestyle='--', label=day)
            
            # save vals to median structure
            for idx, val in enumerate(y_vals): median_vals[idx].append(val)
            print(median_vals)

        median_vals = [
            float(sorted(meds)[len(meds)//2])
            for meds in median_vals
        ]

        x_vals = [pd.to_datetime('10:00:00'), pd.to_datetime('11:00:00'), pd.to_datetime('12:00:00'), pd.to_datetime('13:00:00'),
                  pd.to_datetime('14:00:00'), pd.to_datetime('15:00:00'), pd.to_datetime('16:00:00'), pd.to_datetime('17:00:00')]
        y_vals = median_vals

        ax.plot(x_vals, y_vals, marker='x', linestyle='-', lw=3, label='median')
        
        # set text
        ax.set_xlabel("Time (10:00 AM - 5:00 PM)")
        ax.set_ylabel("dBA Recording (Average)")

        title = f"Average dBA Levels in {loc.capitalize()} by Day"
        ax.set_title(title)

        # format dates
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))

        ax.legend(title="Days")
        ax.grid(True, linestyle='--', alpha=0.6)
        plt.tight_layout()

        filename = f'{loc}_avgs_chart'
        plt.savefig(f'graphics/{filename}.png', dpi=300, bbox_inches='tight')
        print(f"Chart saved successfully as {filename}")

        plt.close()


if __name__ == '__main__':
    data = get_data()
    make_location_linecharts(data)