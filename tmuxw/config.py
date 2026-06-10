"""Lectura de archivos de configuracion estilo tmux.conf (FUNCIONALIDADES.md seccion 9).

Sintaxis tmux: comentarios con '#', comillas simples/dobles, una orden por
linea, continuacion de linea con backslash final.
"""

import os


def tokenize(line: str) -> list:
    """Divide una linea estilo tmux.conf en tokens.

    - Respeta comillas dobles y simples (pueden contener espacios y '#').
    - Backslash escapa el siguiente caracter fuera de comillas simples
      (es decir: sin comillas o dentro de comillas dobles).
    - '#' fuera de comillas inicia comentario SOLO al comienzo de un token
      (como tmux: 'hola-#S' es literal, '... # comentario' se descarta).
    - Linea vacia o solo comentario -> [].
    """
    tokens = []
    current = []
    has_token = False  # distingue token vacio ('') de "sin token"
    in_single = False
    in_double = False
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if in_single:
            if ch == "'":
                in_single = False
            else:
                current.append(ch)
            i += 1
            continue
        if ch == "\\":
            # Escapa el siguiente caracter (fuera de comillas simples).
            if i + 1 < n:
                current.append(line[i + 1])
                i += 2
            else:
                # Backslash final suelto: se conserva literal.
                current.append("\\")
                i += 1
            has_token = True
            continue
        if in_double:
            if ch == '"':
                in_double = False
            else:
                current.append(ch)
            i += 1
            continue
        # Fuera de comillas:
        if ch == "#" and not has_token:
            break  # comentario hasta el final de la linea (solo a inicio de token)
        if ch == '"':
            in_double = True
            has_token = True
            i += 1
            continue
        if ch == "'":
            in_single = True
            has_token = True
            i += 1
            continue
        if ch.isspace():
            if has_token:
                tokens.append("".join(current))
                current = []
                has_token = False
            i += 1
            continue
        current.append(ch)
        has_token = True
        i += 1
    if has_token:
        tokens.append("".join(current))
    return tokens


def load_config(path, execute) -> list:
    """Ejecuta un archivo de configuracion linea a linea.

    Lee `path` (utf-8, errors='replace'). Por cada linea logica cuyo
    tokenize() no sea [], llama execute(tokens). Las excepciones de execute
    se capturan y acumulan como "{path}:{nlinea}: {mensaje}" (nlinea es la
    primera linea fisica de la linea logica). Devuelve la lista de errores.
    Si el archivo no existe devuelve [] sin error.

    Una linea fisica que termina en backslash se une con la siguiente
    (continuacion de linea).
    """
    errors = []
    try:
        path_str = os.fspath(path)
    except TypeError:
        path_str = str(path)
    if not os.path.isfile(path_str):
        return errors
    with open(path_str, "r", encoding="utf-8", errors="replace") as fh:
        physical = fh.readlines()
    i = 0
    n = len(physical)
    while i < n:
        start_line = i + 1
        line = physical[i].rstrip("\r\n")
        i += 1
        while line.endswith("\\") and i < n:
            line = line[:-1] + physical[i].rstrip("\r\n")
            i += 1
        try:
            tokens = tokenize(line)
            if not tokens:
                continue
            execute(tokens)
        except Exception as exc:
            errors.append(f"{path}:{start_line}: {exc}")
    return errors
