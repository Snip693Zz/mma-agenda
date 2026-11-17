Replace the extraction spawn command with a fragment-aware command:

const extraction = spawnSync('python3', [
  '-c',
  'import sys,json; from collector.pfl_card_structure import extract_pairs; json.dump(extract_pairs(sys.stdin.read(), sys.argv[1], allow_fragment=(sys.argv[2] == "official_ajax_response")), sys.stdout)',
  url,
  candidate.card_source,
], {input: candidate.card_html, encoding: 'utf8', maxBuffer: 2000000});

All other behavior remains unchanged.