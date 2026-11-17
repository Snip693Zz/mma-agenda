# Remplacer la logique de sortie :
# if status == 'review_discrepancy': sys.exit(2)
# par :
# if status == 'review_discrepancy': print(json.dumps({'status': status, 'action': 'report_only', 'database_writes': False})); sys.exit(0)
# Les statuts add_fights_proposal et unchanged restent non bloquants.
# Aucune écriture Supabase n'est ajoutée.