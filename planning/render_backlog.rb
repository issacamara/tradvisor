require 'json'
require 'digest'
require 'fileutils'

DIR = __dir__
bundle = JSON.parse(File.read(File.join(DIR, 'backlog.json')))
publication_file = File.join(DIR, 'publication.json')
published = File.exist?(publication_file) ? JSON.parse(File.read(publication_file)) : {}
base = 'https://github.com/' + bundle['repository'] + '/issues/'
gate_url = published.fetch('gate', {}).fetch('url', 'BASELINE_PENDING')
epic_url = published.fetch('epic', {}).fetch('url', 'EPIC_PENDING')
numbers = published.fetch('tickets', {})
by_key = bundle['tickets'].to_h { |t| [t['key'], t] }

def document_links(bundle, published, name)
  found = published.fetch('comments', []).select { |c| c['document'] == name }
  return "#{name.capitalize} baseline (publication pending)" if found.empty?
  found.map { |c| "[#{name.capitalize} part #{c['part']}](#{c['url']})" }.join(', ')
end

def dependency_text(keys, by_key, numbers)
  return 'none' if keys.empty?
  keys.map { |key| numbers[key] ? "##{numbers[key]['number']}" : "#{by_key[key]['id']} (number pending)" }.join(', ')
end

out_of_scope = 'No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.'
bodies = {}
bundle['tickets'].each do |t|
  refs = t['refs'].map do |ref|
    name, sections = ref.split(':', 2)
    "- #{document_links(bundle, published, name)}: sections/trace #{sections}"
  end.join("\n")
  conflicts = bundle['conflicts'].select { |c| [c['a'], c['b']].include?(t['key']) }.map do |c|
    other = c['a'] == t['key'] ? c['b'] : c['a']
    "- #{dependency_text([other], by_key, numbers)}: #{c['paths'].map { |p| '`' + p + '`' }.join(', ')}"
  end
  checks = t['checks'].map { |check| '- [ ] ' + check }.join("\n")
  bodies[t['key']] = <<~MD
    <!-- tradvisor-v1-backlog:#{t['id']} -->
    ## Context
    Tracking epic: #{epic_url}
    Approved public baseline: #{gate_url}
    #{refs}

    ## Scope
    #{t['scope']}

    Owned files/modules (new paths are proposed boundaries, not claims that code exists):
    #{t['files'].map { |p| '- `' + p + '`' }.join("\n")}

    ## Out Of Scope
    #{out_of_scope}
    Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

    ## Contracts
    #{t['contracts']}
    Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

    ## Acceptance Criteria
    #{checks}
    - [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
    - [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

    ## Estimate And Scheduling
    Estimate: #{t['estimate']} (#{t['estimate'] == 'S' ? 'up to 2 hours' : '2-4 hours'} of focused work; not elapsed wait for approvals/evidence).
    Wave: #{t['wave']}
    Domain: #{t['domain']}
    Blocked by: #{dependency_text(t['deps'], by_key, numbers)}
    Blocks: #{dependency_text(t['blocks'], by_key, numbers)}

    Conflict exclusions (not hard dependencies):
    #{conflicts.empty? ? 'none' : conflicts.join("\n")}

    Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
  MD
end

graph = ["flowchart TD"]
bundle['tickets'].each { |t| graph << "  #{t['id'].delete('-')}[\"#{t['id']} #{numbers[t['key']] ? '#' + numbers[t['key']]['number'].to_s : ''}\"]" }
bundle['tickets'].each { |t| t['deps'].each { |d| graph << "  #{by_key[d]['id'].delete('-')} --> #{t['id'].delete('-')}" } }
bundle['conflicts'].each { |c| graph << "  #{by_key[c['a']]['id'].delete('-')} -.- #{by_key[c['b']]['id'].delete('-')}" }

rows = bundle['tickets'].sort_by { |t| [t['wave'], t['id']] }.map do |t|
  target = numbers[t['key']] ? "[##{numbers[t['key']]['number']}](#{numbers[t['key']]['url']})" : t['id']
  "| #{t['wave']} | #{target} #{t['title']} | #{t['estimate']} | #{t['domain']} |"
end.join("\n")
wave_rows = bundle['tickets'].group_by { |t| t['wave'] }.sort.map do |wave, items|
  "| #{wave} | #{items.map { |t| dependency_text([t['key']], by_key, numbers) }.join(', ')} | #{items.length > 1 ? 'May run concurrently after eligibility verification; no shared-file conflicts within this wave' : 'Single task'} | All hard prerequisites are in earlier waves; conflicting owners are serialized |"
end.join("\n")
conflict_rows = bundle['conflicts'].map do |c|
  "| #{dependency_text([c['a']], by_key, numbers)} | #{dependency_text([c['b']], by_key, numbers)} | #{c['paths'].map { |p| '`' + p + '`' }.join(', ')} |"
end.join("\n")
task_list = bundle['tickets'].map { |t| "- [ ] #{dependency_text([t['key']], by_key, numbers)} #{t['title']}" }.join("\n")
epic = <<~MD
  <!-- tradvisor-v1-tracking-epic -->
  ## Scope And Authority
  Approved sanitized baseline: #{gate_url}. Target integration branch: `V1`.
  Seven responsibilities: reused Ingestion, Analytical Data and Pipeline Orchestration; new Analysis Engine, Investor Application, Paper Trading and Application Store.
  Deliver Swing (EMA20/50, RSI14, ATR14, liquidity and versioned entry/exit rules), equal-priority Long-Term Growth/dividend research, and manual recommendation-linked paper trading with reset/recovery protection.
  Static Next.js/TypeScript frontend, FastAPI, shared batch analysis, structured Firestore and existing cloud ingestion foundation. No Dividend/Balanced composite scores or real portfolio tracking in V1.

  ## Governance
  This epic is the scheduling source of truth. No agents are assigned or dispatched. No roster/identity mapping has been established; do not fabricate one. All tickets retain `blocked` while dispatch is disabled, even where `Blocked by: none` means there is no technical predecessor. After graph publication is reconciled, a later explicitly authorized dispatch can evaluate eligibility and change labels.
  One active dispatcher, one ticket per agent; reserve the actual agent and file ownership here before dispatch. Re-read issue/PR state and verify predecessor artifacts merged into V1. A closed/cancelled issue or a wave number is not proof of delivery. Recompute conflicts if scope/files change. Agent tasks are not launched by adding an assignee alone.
  Existing user work must be preserved. Use the original restricted operator evidence for real environment targeting. This public epic contains no environment inventory or credentials. No production cloning/writes, destructive migration, paid run, plan/apply, seed, or schedule activation is authorized by backlog publication. Deployment and release approvals remain separate.
  Estimates: #{bundle['estimates']} Re-split oversized work before assigning; external evidence/approval wait is not implementation time. Review-only tasks require the named role's evidence, not invented sign-off. No milestones or delivery-date promises have been introduced.

  ## Validation
  #{bundle['tickets'].length} tickets, #{bundle['tickets'].map { |t| t['wave'] }.max} waves, #{bundle['conflicts'].length} undirected file-conflict pairs. Required fields, acyclic hard-dependency graph, reverse edges, one wave per ticket, predecessors in earlier waves, conflict-free waves and every ticket's path to final release are validated locally. Public safety scans exclude private paths, environment IDs and inventory. Live publication verification is recorded separately; document checks are not passing application tests.

  ## Tickets And Estimates
  | Wave | Ticket | Estimate | Domain |
  |---|---|---|---|
  #{rows}

  ## Wave Plan
  | Wave | Tickets | Parallelizability | Rationale |
  |---|---|---|---|
  #{wave_rows}

  ## Dependency Graph
  Solid arrows are hard prerequisites. Dotted undirected edges are file-conflict exclusions, not dependencies. Node IDs map to the ticket table; wave planning does not replace current ownership checks.
  ```mermaid
  #{graph.join("\n")}
  ```

  ## Conflict Register
  | Ticket | Conflicts With | Overlapping Files/Modules |
  |---|---|---|
  #{conflict_rows}

  ## Delivery Checklist
  #{task_list}

  ## Reservations And First-Wave Assignments
  None. Dispatch is disabled. First-wave work is technically independent local foundations plus restricted infrastructure/compliance review; no agent availability or authorization is presumed. Infrastructure read/plan permission and legal/operator decisions must be established by the future owner.

  ## Release Gates
  Verify source/company-sector coverage, point-in-time financial evaluation, contract/concurrency tests, complete-workflow accessibility, pilot load/batch targets, measured whole-stack cost, isolated restore drill, legal/privacy/disclaimer review and named operator/support. Final launch requires product-owner acceptance. New development schedules remain paused until activation is explicitly approved. Missing data stays unavailable; never relax scoring or recovery safeguards to make a gate pass.
MD
raise 'Epic too large' if epic.bytesize > 60_000
raise 'Ticket too large' if bodies.values.any? { |body| body.bytesize > 60_000 }
all_public = [epic, *bodies.values].join("\n")
raise 'Private content found' if all_public.match?(%r{/Users/|gs://|gserviceaccount\.com|\b\d{12}\b|dev-tradvisor|prod-tradvisor|default\.tfstate|-----BEGIN})
File.write(File.join(DIR, 'issue_bodies.json'), JSON.pretty_generate({epic: epic, tickets: bodies}) + "\n")
File.write(File.join(DIR, 'tradvisor_backlog.md'), epic)
FileUtils.mkdir_p(File.join(DIR, 'issues'))
bodies.each { |key, body| File.write(File.join(DIR, 'issues', key + '.md'), body) }
puts "Rendered #{bodies.length} ticket bodies; epic #{epic.bytesize} bytes; publication refs #{numbers.length}/#{bundle['tickets'].length}."
