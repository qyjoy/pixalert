# pixalert
Detect the target picture and alert


## V3.0 Changelog:

Coordinate Tracking: When detection is successful, the status bar will display the precise (X, Y) screen coordinates of the target.

History Record: If the target is not detected, the last detection time will still be displayed, making it easier to verify whether it has appeared before.

Anti-Self-Recognition Feature: Added a “👁 Show/Hide Preview” button.

Principle: If the preview is not hidden, the program may detect the preview image within its own window during screen scanning, causing false positives. By hiding the preview, it is replaced with text, completely eliminating the “detecting myself” loop.
