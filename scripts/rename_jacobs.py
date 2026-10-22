import pathlib

def get_old_paths(dir: pathlib.Path):
    
    return [f for f in dir.iterdir() if f.is_file()]
    # get all file names under the directory and return them

def rename_logic(fname: str):

    name = fname.split('_')

    fdate, ftime, floc = name
    print(name)
    # parses date
    date = f'10-{fdate}-26'

    floor = ""
    match floc[:-4]:
        
        # parses the floor
        case "atrium": floor = "floor2_atrium"
        case "study":  floor = "floor1_study"
        case "cafe":   floor = "floor1_cafeteria"
        case _: raise ValueError('ERROR: Could not parse floor attribute')

    time = ""
    match ftime:

        # parses time attribute
        case "10h": time = "10am"
        case "11h": time = "11am"
        case "12h": time = "12pm"
        case "13h": time = "1pm"
        case "14h": time = "2pm"
        case "15h": time = "3pm"
        case "16h": time = "4pm"
        case "17h": time = "5pm"

    return f'{floor}_{time}_{date}.csv'

if '__main__' == __name__:
    pfx = '../data/'
    dir_names = [
        pathlib.Path(pfx + name) for name in ['10-05-26', '10-07-26', '10-08-26']
    ]
    for dir in dir_names:
        fnames = get_old_paths(dir)
        for f in fnames:
            new_name = rename_logic(f.name)
            print(new_name)
            f.rename(new_name)