# JuBe LCP

Conversion of JuBe Corpus for submission to LiRI Corpus Platform (LCP). The corpus was downloaded from Zenodo: https://zenodo.org/records/5648157

Before running the script, make sure to have JuBe downloaded.

## Arguments

- `--data`: Path to the folder containing the source data (default: `./JUBEKO/JUBEKO/Datensatz/Datenerhebung_2019`). It should contain XML files, audio files, and a CSV file with person metadata.
- `--output`: Path to the output folder which will be used for upload to the LCP (default: `./output/`). Audio files will be copied to `output/media/`.
- `--metadata`: Path to the JSON file with corpus metadata (description, date, revision, authors). (default: `./meta.json`)
- `--copy_audio`: (Optional flag) Copy original WAV audio files to the output/media folder. If not set, `.mp3` files are referenced but not copied.
- `--clean_csv`: (Optional flag) Clean the person CSV file from empty rows and rename columns for consistent metadata processing.
- `--limit`: (Optional) Limit the number of files to process. Useful for testing.

## Usage

Run the script via command line:

```sh
python jube_prep/jube_builder.py --data <data_folder> --output <output_folder> --metadata <meta.json> [--copy_audio] [--clean_csv] [--limit N]
```

## Output

The script produces:

- `meta.json` (copied to the output folder)
- LCP corpus files in the output folder
- `global_attribute_speaker.csv` (in the output folder, with speaker metadata)
- Audio files copied to `output/media/` (if `--copy_audio` is set)
- Updated `config.json` in the output folder, with a `"tracks"` key for LCP compatibility

## Notes

- The script now ensures that duplicate speaker IDs are removed from `global_attribute_speaker.csv`.
- The output is cleaned of empty lines for compatibility.
- The `"tracks"` key is automatically added to `config.json` to support LCP's layer splitting by speaker.
- Word timing is proportionally distributed within each sentence, improving alignment accuracy.

You can use `jube_prep` in the command line or run `python -m jube_prep`.

For further processing, you may want to convert the output to