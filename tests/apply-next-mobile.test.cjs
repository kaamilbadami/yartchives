const assert = require('assert');
const fs = require('fs');
const path = require('path');

function runTest() {
    console.log('Running Apply Next Mobile Layout Structural Contract...');
    const cssPath = path.join(__dirname, '..', 'apply-next.css');
    const content = fs.readFileSync(cssPath, 'utf8');

    // Check for media query and required modifications
    const hasMobileMedia = content.includes('@media (max-width: 720px)');
    assert(hasMobileMedia, 'Expected @media (max-width: 720px) to be present');

    // Ensure actions use a grid to prevent ugly flex wrapping
    const actionsGridPattern = /\.apply-next-actions\s*{[^}]*display:\s*grid/is;
    assert(actionsGridPattern.test(content), 'Expected .apply-next-actions to use display: grid on mobile');

    // Ensure tabs stretch evenly
    const tabsFlexPattern = /\.apply-next-view-tabs\s*{[^}]*display:\s*flex/is;
    assert(tabsFlexPattern.test(content), 'Expected .apply-next-view-tabs to use flex for horizontal scaling');

    // Verify primary button explicitly overrides to full width in grid
    const primaryFullPattern = /\.apply-next-actions\s+\.primary-btn\s*{[^}]*grid-column:\s*1\s*\/\s*-1/is;
    assert(primaryFullPattern.test(content), 'Expected .primary-btn to span the grid layout horizontally');

    console.log('Mobile layout contract passed.');
}

runTest();
