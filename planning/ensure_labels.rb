require 'json'
require 'open3'

bundle = JSON.parse(File.read(File.join(__dir__, 'backlog.json')))
repo = bundle.fetch('repository')
output, error, status = Open3.capture3('gh', 'api', "repos/#{repo}/labels?per_page=100")
abort error unless status.success?
existing = JSON.parse(output).map { |label| label.fetch('name') }
created = []
bundle.fetch('labels').each do |name|
  next if existing.include?(name)
  color = name.start_with?('wave-') ? 'bfd4f2' : name.start_with?('domain:') ? 'c2e0c6' : 'd4c5f9'
  description = name == 'blocked' ? 'Not dispatchable: dependency, approval, or explicit dispatch hold' : 'Tradvisor V1 architecture delivery classification'
  output, error, status = Open3.capture3('gh', 'api', '--method', 'POST', "repos/#{repo}/labels", '-f', "name=#{name}", '-f', "color=#{color}", '-f', "description=#{description}")
  unless status.success?
    abort "STOP: failed label #{name}; created #{created.join(', ')}; reconcile before retry. #{error}"
  end
  result = JSON.parse(output)
  abort "STOP: unexpected label response for #{name}" unless result['name'] == name
  created << name
end
puts "Verified label setup; created #{created.length}, preserved #{existing.length} existing labels."
