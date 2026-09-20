require 'json'
require 'digest'
require 'fileutils'

ROOT = File.expand_path('..', __dir__)
OUT = File.join(__dir__, 'public')
FileUtils.mkdir_p(OUT)

def replace_section(text, number, replacement)
  text.sub(/^## #{number}\. .*?(?=^## #{number + 1}\.)/m, replacement + "\n\n")
end

docs = {}
architecture = File.read(File.join(ROOT, 'tradvisor_architecture.md'))
architecture = replace_section(architecture, 6, <<~MD)
  ## 6. Reuse Inventory

  Reuse the existing Python source adapters, financial PDF extraction and loading stages,
  company discovery/mapping, BigQuery load helpers, Terraform foundation and CI workflow.
  These are reuse candidates, not certified live services. Adapt source-specific contracts,
  retry-safe loading, immutable evidence and explicit pipeline dependencies.

  Detailed environment inventory, state addresses, identities and observed security findings
  remain in restricted operator evidence and are intentionally not published here.
  Before deployment, verify current ownership and preserve existing development resources.
  Production is a read-only functional reference, not a configuration/state/data clone.
MD
architecture = architecture.lines.reject do |line|
  line.include?('production commit') || line.start_with?('Deployment preparation update,') ||
    line.include?('Existing development state owns resources omitted') ||
    line.include?('Production references or stale state copied') ||
    line.start_with?('**Document validation')
end.join
architecture = architecture.sub(/^\*\*Deployment gate:\*\*.*$/, '**Deployment gate:** Keep environment configuration, identities and state isolated. Verify current ownership using restricted operator evidence; preserve existing development resources. No production writes, state/secret/user cloning, unapproved deletion or automatic activation. Concrete plans, applies, data seeding and schedule activation each require separate approval.')
architecture = architecture.sub(/^- Deployment:.*$/, '- Deployment: V1 targets the existing development environment. Preserve existing resources and isolate configuration, identities, state and data. Use production as a read-only functional baseline. New schedules remain paused until dependency/cost checks and separate activation approval. Restricted infrastructure evidence is available only to authorized operators; do not publish it in issues or logs.')
architecture = architecture.gsub('Existing legacy `trading_dashboard.users` tables and development web resources are not this ledger and must be preserved; no identity/data migration is implied.', 'Existing application data is not this ledger and must be preserved; no identity/data migration is implied.')
architecture = architecture.gsub('preserve uppercase tables and legacy users', 'preserve existing tables and application data')
architecture = architecture.gsub('preserved legacy indices', 'preserved existing resource addresses')
architecture = architecture.gsub('retain missing legacy declarations and addresses, current schedules and IAM members', 'preserve verified existing ownership, schedules and access')
architecture = architecture.gsub('Backend prefixes and state addresses are now evidenced', 'Backend ownership requires operator verification')
architecture = architecture.gsub('Do not dispatch agents or create GitHub issues as part of this document-finalization step.', 'The earlier document-finalization step did not authorize dispatch. The stakeholder has now separately authorized sanitized baseline and backlog publication; agents remain unassigned.')
docs['architecture'] = architecture
docs['financial'] = File.read(File.join(ROOT, 'tradvisor_financial_contract.md'))
docs['api'] = File.read(File.join(ROOT, 'tradvisor_api_data_contract.md'))
docs['integration'] = File.read(File.join(ROOT, 'tradvisor_integration_draft.md'))
mapping = File.read(File.join(ROOT, 'tradvisor_source_mapping.md'))
mapping = replace_section(mapping, 2, <<~MD)
  ## 2. Evidence And Status Convention

  Private source samples and schema metadata informed this mapping but are not reproduced
  or linked publicly. They do not certify full history, source semantics or usable coverage.
  The intended price date is the trading date and volume counts individual shares. Source
  session attribution and zero-volume price meaning still require adapter verification.
  Financial scope, units, owner attribution and required additional fields remain unverified.
  A missing fiscal year must remain missing; only one dividend year is currently available.

  Available means a field is present, not semantically verified. Confirm means evidence is
  needed. Derive means deterministic computation after prerequisites. Add means normalized
  metadata/state is needed. Unavailable means not evidenced. Deferred means outside V1.

  Preserve supported facts and metrics. Publish complete Growth scores only with all
  required inputs; never reweight partial totals or invent missing history. Report company
  and sector coverage and blocking inputs for product-owner acceptance before launch.
  Insufficient coverage requires explicit scope review, not a silent formula change.
MD
mapping = mapping.lines.reject { |l| l.start_with?('There are 317 distinct') }.join
docs['mapping'] = mapping

docs.transform_values! do |body|
  body.gsub(/dev-tradvisor|prod-tradvisor/, 'environment-id-withheld')
      .gsub(/\[([^\]]+)\]\((tradvisor_[^)]+\.md)\)/, '\1 (companion baseline document)')
      .gsub(/\[([^\]]+)\]\((archive\/[^)]+)\)/, '`\2`')
      .gsub('Architecture v0.38', 'Architecture v1.0')
      .gsub('API/data contract v0.12', 'API/data contract v0.13')
      .gsub('SHEC 2024', 'A potentially missing fiscal year')
      .gsub('The supplied SHEC sample contains 2021, 2022, 2023 and 2025; 2024 is unconfirmed in the full source, not established as absent market-wide.', 'Private samples do not establish consecutive full-source fiscal coverage; do not infer market-wide gaps from a sample.')
      .gsub('SHEC sample has four nonconsecutive years.', 'Private samples do not certify five consecutive years.')
      .gsub('current Terraform specifies Python 3.9 while CI checks Python 3.11.', 'runtime compatibility remains implementation verification.')
end

docs.each do |key, body|
  raise "Sensitive public content: #{key}" if body.match?(%r{/Users/|gs://|gserviceaccount\.com|\b\d{12}\b|dev-tradvisor|prod-tradvisor|default\.tfstate|-----BEGIN})
  File.write(File.join(OUT, "#{key}.md"), "<!-- Public derivative: operational identifiers and private inventory excluded. Normative behavior unchanged. -->\n\n" + body)
end

TICKETS = []
def ticket(key, title, domain, refs, deps, files, scope, contracts, checks, estimate = 'M')
  TICKETS << {key: key, id: format('V1-%03d', TICKETS.length + 1), title: title,
              domain: domain, refs: refs, deps: deps, files: files, scope: scope,
              contracts: contracts, checks: checks, estimate: estimate}
end

# Each scope is limited to one implementation/review session; paths absent today are proposed ownership boundaries.
load File.join(__dir__, 'tickets.rb')
# Foundations and the daily position projection are explicit rather than implied by wave order.
ticket('bootstrap', 'Establish isolated Python package and fixture test foundations', 'contracts', ['architecture:13; ORCH-01,NFR-03'], [], ['backend/pyproject.toml', 'backend/__init__.py', 'tests/conftest.py'], 'Set up pinned backend package/test dependencies and credential-free fixture/emulator configuration without moving or overwriting legacy ingestion code.', 'Expose local test/type commands and shared fixture boundaries; no business implementation.', ['Clean checkout can run a smoke test and import backend without external calls.', 'Tests do not require cloud credentials; preserve dirty user files and existing ingestion paths.'], 'S')
ticket('holding_projection', 'Persist session-ordered position exit references', 'paper', ['architecture:7; FR-SW-06,NFR-02'], ['holding', 'fill', 'store'], ['backend/paper/project_holding.py', 'tests/paper/project_holding/'], 'Advance high-water, latched activation, evaluated-through session and generation-bound advice from each eligible daily close using historical position state and frozen exit policy.', 'Consume immutable execution/indicator histories; expose transactionally versioned current holding references to reads and acceptance.', ['Retries and out-of-order batches cannot regress state or activate from an old high using a later entry price.', 'Test additional buys, partial sells, close/reopen, missing closes and reset races; duration still advances on exchange sessions.'])
ticket('monitoring_config', 'Configure bounded operational alerts and log retention', 'infrastructure', ['architecture:9; NFR-08,NFR-09'], ['observability', 'store_infra', 'runtime'], ['terraform/', 'tests/infrastructure/monitoring/'], 'Add development alert/log-lifecycle configuration and a bounded backup-health check for the emitted operational signals; preserve existing monitoring resources.', 'Consume telemetry definitions and private operator destination; expose reviewable configuration, no automatic activation.', ['Failed/overdue backups, stale publication and worker failures map to actionable alerts without credential/personal-data disclosure.', 'Thirty-day application-log policy and finite check cadence are explicit; no request keep-alive or always-on worker.'])
TICKETS.find { |t| t[:key] == 'scalars' }[:deps] << 'bootstrap'
TICKETS.find { |t| t[:key] == 'client' }[:deps] << 'shell'
TICKETS.find { |t| t[:key] == 'ci' }[:files].delete('backend/pyproject.toml')
TICKETS.find { |t| t[:key] == 'reads' }[:deps] << 'holding_projection'
TICKETS.find { |t| t[:key] == 'pipeline_integration' }[:deps] << 'holding_projection'
TICKETS.find { |t| t[:key] == 'pipeline_integration' }[:scope] += ' Wire daily holding projection and eligible pending-order processing after their input readiness, without creating orders.'
TICKETS.find { |t| t[:key] == 'release' }[:deps] << 'monitoring_config'
by_key = TICKETS.to_h { |t| [t[:key], t] }
raise 'Duplicate keys' unless by_key.length == TICKETS.length
TICKETS.each do |t|
  %i[title domain refs files scope contracts checks estimate].each { |field| raise "Missing #{field}: #{t[:key]}" if t[field].nil? || t[field].empty? }
  raise "Missing dependency #{t[:key]}" unless t[:deps].all? { |d| by_key.key?(d) && d != t[:key] }
  raise "Too few tests #{t[:key]}" unless t[:checks].length >= 2
  raise "Unbounded estimate #{t[:key]}" unless %w[S M].include?(t[:estimate])
end
ordered = []
until ordered.length == TICKETS.length
  eligible = TICKETS.reject { |t| ordered.include?(t) }.select { |t| (t[:deps] - ordered.map { |x| x[:key] }).empty? }
  raise 'Cyclic dependency graph' if eligible.empty?
  ordered.concat(eligible)
end

def overlap(a, b)
  a[:files].product(b[:files]).select do |x, y|
    x == y || x.start_with?(y.end_with?('/') ? y : y + '/') || y.start_with?(x.end_with?('/') ? x : x + '/')
  end.map { |pair| pair.min_by(&:length) }.uniq
end
conflicts = TICKETS.combination(2).map do |a, b|
  paths = overlap(a, b)
  {a: a[:key], b: b[:key], paths: paths} unless paths.empty?
end.compact
ordered.each do |t|
  wave = (t[:deps].map { |d| by_key[d][:wave] }.max || 0) + 1
  while ordered.any? { |other| other[:wave] == wave && !overlap(t, other).empty? }
    wave += 1
  end
  t[:wave] = wave
  t[:blocks] = TICKETS.select { |other| other[:deps].include?(t[:key]) }.map { |other| other[:key] }
end
TICKETS.each do |t|
  raise 'Invalid wave' unless t[:deps].all? { |d| by_key[d][:wave] < t[:wave] }
end
conflicts.each { |c| raise 'Wave file conflict' if by_key[c[:a]][:wave] == by_key[c[:b]][:wave] }
TICKETS.each do |t|
  reachable = [t[:key]]
  reachable.each { |key| reachable.concat(by_key[key][:blocks] - reachable) }
  raise "Orphaned delivery work: #{t[:key]}" unless reachable.include?('release')
end

chunks = []
docs.each do |key, body|
  parts = []
  part = ''
  in_fence = false
  body.each_line do |line|
    if part.bytesize + line.bytesize > 43_000 && !in_fence
      parts << part
      part = ''
    end
    part += line
    in_fence = !in_fence if line.start_with?('```')
  end
  parts << part unless part.empty?
  parts.each_with_index do |text, i|
    comment = "## Public Baseline: #{key.capitalize} (#{i + 1}/#{parts.length})\n\n" + text
    raise 'Comment too large' if comment.bytesize > 60_000
    chunks << {document: key, part: i + 1, body: comment, sha256: Digest::SHA256.hexdigest(comment)}
  end
end
labels = ['blocked', 'agent-ready', 'epic', 'architecture'] + TICKETS.map { |t| "domain:#{t[:domain]}" }.uniq + TICKETS.map { |t| "wave-#{t[:wave]}" }.uniq
bundle = {repository: 'issacamara/tradvisor', integration_branch: 'V1', tickets: ordered,
          conflicts: conflicts, comments: chunks, labels: labels, dispatch: 'disabled; no roster or assignments',
          estimates: 'S: up to 2 hours; M: 2-4 hours. Split before implementation if scope exceeds half a day.'}
File.write(File.join(__dir__, 'backlog.json'), JSON.pretty_generate(bundle) + "\n")
puts "Validated #{TICKETS.length} atomic tickets, #{TICKETS.map { |t| t[:wave] }.max} waves, #{conflicts.length} conflict pairs, #{chunks.length} baseline comments."
