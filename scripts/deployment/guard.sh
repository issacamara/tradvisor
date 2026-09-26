#!/usr/bin/env bash
set -euo pipefail

: "${GITHUB_REF_NAME:?GITHUB_REF_NAME is required}"
: "${TF_VAR_project_id:?TF_VAR_project_id is required}"
: "${TF_STATE_BUCKET:?TF_STATE_BUCKET is required}"
: "${TF_STATE_PREFIX:?TF_STATE_PREFIX is required}"

[[ "${GITHUB_REF_NAME}" == "V1" ]] || { echo "deployment is allowed only from V1" >&2; exit 1; }
[[ "${TF_VAR_project_id}" == "dev-tradvisor" ]] || { echo "deployment is allowed only for dev-tradvisor" >&2; exit 1; }
[[ "${TF_STATE_BUCKET}" == "dev-tradvisor-tfstate" ]] || { echo "unexpected Terraform state bucket" >&2; exit 1; }
[[ "${TF_STATE_PREFIX}" == state/dev ]] || { echo "unexpected Terraform state prefix" >&2; exit 1; }
[[ "${DEPLOY_ACTION:-plan}" == "plan" || "${DEPLOY_ACTION:-plan}" == "apply" ]] || { echo "invalid deployment action" >&2; exit 1; }

echo "validated development delivery context for ${DEPLOY_ACTION:-plan}"
