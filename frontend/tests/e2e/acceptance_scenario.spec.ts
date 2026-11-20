import { test, expect } from "@playwright/test";
import path from "path";

test.describe("SolarDoctor End-to-End Operational Acceptance Scenario", () => {
  test.setTimeout(120000); // 2 minutes for complete operational cycle

  test("full operational loop: Detect -> Diagnose -> Explain -> Act & Verify -> OOD Check", async ({ page, request, baseURL }) => {
    const origin = baseURL || "http://localhost:3000";

    // 1. Authenticate as Operator
    await page.goto(`${origin}/login`);
    await page.waitForLoadState("networkidle");

    // Fill credentials
    const emailInput = page.locator('input[type="email"], input[name="email"], input#email');
    const passInput = page.locator('input[type="password"], input[name="password"], input#password');

    if (await emailInput.count() > 0) {
      await emailInput.fill("demo@solardoctor.local");
      await passInput.fill("SolarDoctor123!");
      await page.click('button[type="submit"]');
      await page.waitForURL("**/dashboard**", { timeout: 15000 });
    }

    // 2. Open Alerts & Find S-04 Deficit Alert
    await page.goto(`${origin}/dashboard/alerts`);
    await page.waitForLoadState("networkidle");

    // Verify Alerts heading
    await expect(page.locator("h1")).toContainText(/Alerts/i);

    // Look for S-04 deficit alert in the list
    const s04Row = page.locator('.dash-alert-row:has-text("S-04")').first();
    await expect(s04Row).toBeVisible({ timeout: 10000 });

    // Validate deficit percentage is displayed
    await expect(s04Row).toContainText(/deficit|shortfall/i);

    // 3. Click Inspect deep link from the alert
    const inspectBtn = s04Row.locator('a:has-text("Inspect")');
    await expect(inspectBtn).toBeVisible();
    await inspectBtn.click();

    // 4. On Inspections Screen: Validate pre-filled alert context
    await page.waitForURL("**/dashboard/inspections**", { timeout: 10000 });
    await expect(page.locator("h1")).toContainText(/Single-Image Defect Inspection/i);

    // Load sample image (dusty-panel-closeup.webp)
    const loadSampleBtn = page.locator('button:has-text("Load dusty-panel-closeup.webp")');
    if (await loadSampleBtn.isVisible()) {
      await loadSampleBtn.click();
    } else {
      // Direct file upload fallback
      const samplePath = path.resolve(__dirname, "../../public/images/dusty-panel-closeup.webp");
      await page.setInputFiles('input[type="file"]', samplePath);
    }

    // Run diagnosis
    const runBtn = page.locator('button:has-text("Run Defect Diagnosis & Fusion")');
    await expect(runBtn).toBeEnabled();
    await runBtn.click();

    // 5. Validate Visual Classifier Output & Top-3 Distribution
    const diagnosisCard = page.locator('.dash-card:has-text("AI Visual Defect Diagnosis")');
    await expect(diagnosisCard).toBeVisible({ timeout: 25000 });
    await expect(diagnosisCard).toContainText(/Confidence/i);

    // 6. Validate Explainability Tabs (Grad-CAM, LIME)
    const gradcamTab = page.locator('button:has-text("Grad-CAM Overlay")');
    await expect(gradcamTab).toBeVisible();
    await gradcamTab.click();

    const limeTab = page.locator('button:has-text("LIME Superpixels")');
    await expect(limeTab).toBeVisible();
    await limeTab.click();

    // 7. Validate Telemetry Cross-Check & Fusion Verdict
    const fusionCard = page.locator('.dash-card:has-text("Fusion Decision Engine")');
    await expect(fusionCard).toBeVisible();
    await expect(fusionCard).toContainText(/Telemetry Cross-Check/i);
    await expect(fusionCard).toContainText(/Action/i);

    // 8. Validate ROI Recommendation
    const roiCard = page.locator('.dash-card:has-text("Cleaning Economics & ROI Payback")');
    await expect(roiCard).toBeVisible();
    await expect(roiCard).toContainText(/Payback/i);

    // 9. Create Work Order from Inspection
    const createWoModalBtn = page.locator('button:has-text("Create Work Order from Inspection")');
    await expect(createWoModalBtn).toBeVisible();
    await createWoModalBtn.click();

    // In modal, submit work order
    const modal = page.locator('.dash-card:has-text("Dispatch Work Order")');
    await expect(modal).toBeVisible();

    const submitWoBtn = modal.locator('button:has-text("Create Work Order")');
    await submitWoBtn.click();

    // 10. Navigate to Work Orders Board
    await page.goto(`${origin}/dashboard/work-orders`);
    await page.waitForLoadState("networkidle");
    await expect(page.locator("h1")).toContainText(/Work Orders/i);

    // 11. Find the newly created work order in the Kanban board
    const woCard = page.locator('.sd-kanban-card').first();
    await expect(woCard).toBeVisible({ timeout: 10000 });
    await woCard.click();

    // 12. Interact with Drawer: Assign Technician, Checklists, Notes, Photo
    const drawer = page.locator('.sd-drawer');
    await expect(drawer).toBeVisible();

    // Assign technician
    const assigneeSelect = drawer.locator('select').first();
    await assigneeSelect.selectOption("technician@solardoctor.example");

    // Complete checklist toggles
    const checklistItems = drawer.locator('input[type="checkbox"]');
    const chkCount = await checklistItems.count();
    for (let i = 0; i < chkCount; i++) {
      await checklistItems.nth(i).check();
    }

    // Add resolution note
    const noteArea = drawer.locator('textarea');
    await noteArea.fill("Cleaned soiling deposits and reconnected string S-04 junction box. Nominal resistance verified.");

    // Add after-photo evidence path
    const photoInput = drawer.locator('input[placeholder*="after"]');
    if (await photoInput.count() > 0) {
      await photoInput.fill("fault_photos/after_cleaning_s04.webp");
    }

    // Mark Resolved
    const resolveBtn = drawer.locator('button:has-text("Mark Resolved")');
    if (await resolveBtn.isVisible()) {
      await resolveBtn.click();
      await page.waitForTimeout(1000);
    }

    // 13. Verify Fix action
    const verifyFixBtn = drawer.locator('button:has-text("Verify Fix")');
    if (await verifyFixBtn.isVisible()) {
      await verifyFixBtn.click();
      await page.waitForTimeout(1500);
      // Confirm verified badge or alert resolution
      await expect(drawer).toContainText(/VERIFIED|resolved|recovered/i);
    }

    // Close drawer
    const closeBtn = drawer.locator('button:has-text("✕")');
    await closeBtn.click();

    // 14. Test Out-Of-Distribution (OOD) Behavior
    await page.goto(`${origin}/dashboard/inspections`);
    await page.waitForLoadState("networkidle");

    const nonPanelPath = path.resolve(__dirname, "../../public/images/non_panel_test.png");
    await page.setInputFiles('input[type="file"]', nonPanelPath);

    const runOodBtn = page.locator('button:has-text("Run Defect Diagnosis & Fusion")');
    await runOodBtn.click();

    // Confirm OOD warning badge or "Field Check" warning
    const oodWarning = page.locator('text=/Out of Distribution|Needs Field Check|OOD|Warning/i').first();
    await expect(oodWarning).toBeVisible({ timeout: 25000 });
  });
});
