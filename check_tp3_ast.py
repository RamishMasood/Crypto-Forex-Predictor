import ast

with open('src/strategies/streamer_playbook.py', encoding='utf-8') as f:
    tree = ast.parse(f.read())

for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef):
        for m in node.body:
            if isinstance(m, ast.FunctionDef) and m.name == 'evaluate':
                # Check all return statements or dictionary literals with 'tp3'
                has_tp3 = False
                for sub in ast.walk(m):
                    if isinstance(sub, ast.Name) and sub.id == 'tp3':
                        has_tp3 = True
                        break
                if has_tp3:
                    # Check where tp3 is assigned
                    assigned_names = [target.id for stmt in ast.walk(m) if isinstance(stmt, ast.Assign) for target in stmt.targets if isinstance(target, ast.Name)]
                    # check tuple assigns like a = b = c = ...
                    tuple_assigns = []
                    for stmt in ast.walk(m):
                        if isinstance(stmt, ast.Assign):
                            for t in stmt.targets:
                                if isinstance(t, ast.Tuple):
                                    tuple_assigns.extend([e.id for e in t.elts if isinstance(e, ast.Name)])
                    all_assigned = set(assigned_names + tuple_assigns)
                    if 'tp3' not in all_assigned:
                        print(f"CLASS {node.name} MISSING TP3 ASSIGNMENT!")
print("AST check finished.")
