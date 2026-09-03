#!/usr/bin/env bash
# Mutation gate — CLAUDE.md § "Tests and quality".
#
# La cobertura dice si una línea SE EJECUTÓ; la mutación dice si algún test se
# habría enterado de que estaba mal. Un test sin un solo assert da 100% de
# cobertura y 0% aquí: por eso esta puerta es aparte, no en lugar de aquélla.
#
# El criterio de este repo es **cero supervivientes** sobre los cuatro módulos
# puros de [tool.mutmut] (config.py, hostenv.py, pipeline/plan.py,
# pipeline/rom.py) — muy por encima del suelo del 60% que fija la plantilla. Son
# lógica de decisión pura y ~130 mutantes tardan un par de segundos, así que aquí
# el 100% es barato; ese suelo es para cuando deje de serlo, no un objetivo al que
# bajarse.
#
# Lo usan el hook de pre-push y el job `mutation` de CI: una sola fuente, para que
# no puedan divergir.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

command -v mutmut >/dev/null 2>&1 || {
  echo "error: mutmut no está instalado — pip install -e '.[dev]'" >&2; exit 127; }

# mutmut 3.7 sale 0 aunque sobrevivan mutantes (comprobado saboteando una rama a
# propósito), así que el veredicto NO puede ser su código de salida.
mutmut run || true

if mutmut results | grep -qi survived; then
  echo "::error::Surviving mutants in the pure decision modules"
  mutmut results
  echo
  echo "Un mutante vivo es código CUBIERTO PERO SIN VERIFICAR: la línea se ejecuta y" >&2
  echo "ningún assert mira el resultado. Mira el diff exacto con:" >&2
  echo "    mutmut show '<nombre del mutante>'" >&2
  echo "y mátalo afirmando sobre el valor concreto — no recalculándolo con la misma" >&2
  echo "expresión que el código, que se mueve con la mutación y le da la razón." >&2
  echo "Detalle: docs/MUTATION_TESTING.md" >&2
  exit 1
fi
echo "All mutants killed."
