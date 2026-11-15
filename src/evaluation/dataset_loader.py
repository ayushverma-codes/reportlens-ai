"""Load the supplied immutable evaluation set; never fabricate expected answers."""
from pathlib import Path
import csv, json

def load_ground_truth(folder='evaluation/ground_truth'):
    root = Path(folder)
    json_path = root / 'tcs_rag_ground_truth_35.json'
    csv_path = root / 'tcs_rag_ground_truth_35.csv'
    if json_path.exists():
        return json.loads(json_path.read_text(encoding='utf8'))
    if csv_path.exists():
        with csv_path.open(encoding='utf8-sig', newline='') as handle:
            return list(csv.DictReader(handle))
    raise FileNotFoundError('Missing tcs_rag_ground_truth_35.json and tcs_rag_ground_truth_35.csv; provide original evaluation data.')
