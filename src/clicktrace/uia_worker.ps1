Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName WindowsBase
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class UiaWindowOwner {
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint processId);
}
'@

$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ownProcessId = [int]$args[0]
$walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker

while ($null -ne ($line = [Console]::In.ReadLine())) {
    $result = 'NO_PATTERN'
    $actionStarted = $false
    try {
        $parts = $line.Split("`t")
        $point = [System.Windows.Point]::new([double]$parts[0], [double]$parts[1])
        $element = [System.Windows.Automation.AutomationElement]::FromPoint($point)
        $pointElement = $element
        for ($depth = 0; $null -ne $element -and $depth -lt 16; $depth++) {
            $current = $element.Current
            $windowProcessId = [uint32]0
            $nativeWindow = [IntPtr]$current.NativeWindowHandle
            if ($nativeWindow -ne [IntPtr]::Zero) {
                [void][UiaWindowOwner]::GetWindowThreadProcessId($nativeWindow, [ref]$windowProcessId)
            }
            if ($current.ProcessId -eq $ownProcessId -or $windowProcessId -eq $ownProcessId) {
                $result = 'SELF'
                break
            }

            $pattern = $null
            if ($element.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$pattern)) {
                $actionStarted = $true
                $pattern.Invoke()
                $result = 'INVOKED'
                break
            }
            $pattern = $null
            if ($element.TryGetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern, [ref]$pattern)) {
                $actionStarted = $true
                $pattern.Toggle()
                $result = 'TOGGLED'
                break
            }
            $pattern = $null
            if ($element.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$pattern)) {
                $actionStarted = $true
                $pattern.Select()
                $result = 'SELECTED'
                break
            }
            $element = $walker.GetParent($element)
        }

        # Some providers (notably Chromium web documents) return the document
        # from FromPoint even when an actionable descendant occupies the point.
        # Search only that hit subtree, then choose the smallest actionable
        # control whose bounds contain the requested screen coordinate.
        if ($result -eq 'NO_PATTERN' -and $null -ne $pointElement) {
            $matchingControls = [System.Collections.Generic.List[object]]::new()
            $actionableTypes = @(
                [System.Windows.Automation.ControlType]::Button,
                [System.Windows.Automation.ControlType]::Hyperlink,
                [System.Windows.Automation.ControlType]::CheckBox,
                [System.Windows.Automation.ControlType]::RadioButton,
                [System.Windows.Automation.ControlType]::ComboBox,
                [System.Windows.Automation.ControlType]::ListItem,
                [System.Windows.Automation.ControlType]::MenuItem,
                [System.Windows.Automation.ControlType]::TabItem,
                [System.Windows.Automation.ControlType]::TreeItem,
                [System.Windows.Automation.ControlType]::DataItem,
                [System.Windows.Automation.ControlType]::SplitButton,
                [System.Windows.Automation.ControlType]::Custom
            )
            $conditions = @(
                foreach ($controlType in $actionableTypes) {
                    [System.Windows.Automation.PropertyCondition]::new(
                        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
                        $controlType
                    )
                }
            )
            $actionableCondition = [System.Windows.Automation.OrCondition]::new(
                [System.Windows.Automation.Condition[]]$conditions
            )
            $descendants = $pointElement.FindAll(
                [System.Windows.Automation.TreeScope]::Descendants,
                $actionableCondition
            )
            foreach ($candidate in $descendants) {
                $current = $candidate.Current
                $bounds = $current.BoundingRectangle
                if ($bounds.IsEmpty -or $point.X -lt $bounds.Left -or $point.X -gt $bounds.Right -or $point.Y -lt $bounds.Top -or $point.Y -gt $bounds.Bottom) {
                    continue
                }

                $windowProcessId = [uint32]0
                $nativeWindow = [IntPtr]$current.NativeWindowHandle
                if ($nativeWindow -ne [IntPtr]::Zero) {
                    [void][UiaWindowOwner]::GetWindowThreadProcessId($nativeWindow, [ref]$windowProcessId)
                }
                if ($current.ProcessId -eq $ownProcessId -or $windowProcessId -eq $ownProcessId) {
                    $result = 'SELF'
                    break
                }

                $pattern = $null
                $kind = $null
                if ($candidate.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$pattern)) {
                    $kind = 'INVOKED'
                } else {
                    $pattern = $null
                    if ($candidate.TryGetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern, [ref]$pattern)) {
                        $kind = 'TOGGLED'
                    } else {
                        $pattern = $null
                        if ($candidate.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$pattern)) {
                            $kind = 'SELECTED'
                        }
                    }
                }
                if ($kind) {
                    $matchingControls.Add([pscustomobject]@{
                        Area = [double]($bounds.Width * $bounds.Height)
                        Kind = $kind
                        Pattern = $pattern
                    })
                }
            }

            if ($matchingControls.Count -gt 0) {
                $target = $matchingControls | Sort-Object -Property Area | Select-Object -First 1
                $actionStarted = $true
                switch ($target.Kind) {
                    'INVOKED' { $target.Pattern.Invoke() }
                    'TOGGLED' { $target.Pattern.Toggle() }
                    'SELECTED' { $target.Pattern.Select() }
                }
                $result = $target.Kind
            }
        }
    } catch {
        $result = if ($actionStarted) { 'ERROR' } else { 'NO_PATTERN' }
    }
    [Console]::Out.WriteLine($result)
    [Console]::Out.Flush()
}
