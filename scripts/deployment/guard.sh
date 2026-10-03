#!/usr/bin/env bash
set -euo pipefail

: "${GITHUB_REF_NAME:?GITHUB_REF_NAME is required}"
: "${TF_VAR_project_id:?TF_VAR_project_id is required}"
: "${TF_STATE_BUCKET:?TF_STATE_BUCKET is required}"
: "${TF_STATE_PREFIX:?TF_STATE_PREFIX is required}"
: "${DEPLOY_ENV:?DEPLOY_ENV is required}"
: "${ALLOWED_BRANCH:?ALLOWED_BRANCH is required}"
: "${EXPECTED_PROJECT_ID:?EXPECTED_PROJECT_ID is required}"
: "${EXPECTED_STATE_BUCKET:?EXPECTED_STATE_BUCKET is required}"
: "${EXPECTED_STATE_PREFIX:?EXPECTED_STATE_PREFIX is required}"

[[ "${GITHUB_REF_NAME}" == "${ALLOWED_BRANCH}" ]] || { echo "deployment is not allowed from ${GITHUB_REF_NAME} for ${DEPLOY_ENV}" >&2; exit 1; }
[[ "${TF_VAR_project_id}" == "${EXPECTED_PROJECT_ID}" ]] || { echo "unexpected project for ${DEPLOY_ENV}" >&2; exit 1; }
[[ "${TF_STATE_BUCKET}" == "${EXPECTED_STATE_BUCKET}" ]] || { echo "unexpected Terraform state bucket for ${DEPLOY_ENV}" >&2; exit 1; }
[[ "${TF_STATE_PREFIX}" == "${EXPECTED_STATE_PREFIX}" ]] || { echo "unexpected Terraform state prefix for ${DEPLOY_ENV}" >&2; exit 1; }
[[ "${DEPLOY_ACTION:-plan}" == "plan" || "${DEPLOY_ACTION:-plan}" == "import" || "${DEPLOY_ACTION:-plan}" == "apply" ]] || { echo "invalid deployment action" >&2; exit 1; }

echo "validated ${DEPLOY_ENV} delivery context for ${DEPLOY_ACTION:-plan}"
