@{
    # Used by CI (.github/workflows/ci.yml) and by hand:
    #   Invoke-ScriptAnalyzer -Path scripts -Recurse -Settings .\PSScriptAnalyzerSettings.psd1
    Severity     = @('Error', 'Warning')
    ExcludeRules = @(
        # The scripts are interactive console tools; Write-Host is their user interface.
        'PSAvoidUsingWriteHost'
    )
}
