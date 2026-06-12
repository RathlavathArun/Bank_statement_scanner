import { expect, test } from "@playwright/test";

const statementId = "stmt-phase-2";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("access_token", "e2e-token");
  });

  await page.route("**/api/v1/auth/me", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        data: { user: { full_name: "Phase Tester", firm: { name: "QA Firm" } } },
      }),
    });
  });

  await page.route("**/api/v1/statements?page=1&size=20", async (route) => {
    if (route.request().method() === "DELETE") {
      expect(route.request().headers().authorization).toBe("Bearer e2e-token");
      await route.fulfill({ status: 204 });
      return;
    }

    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        data: {
          items: [
            {
              id: statementId,
              filename: "sample-hdfc-statement.csv",
              bank_code: "hdfc",
              status: "READY_FOR_REVIEW",
              transaction_count: 2,
            },
          ],
          total: 1,
          page: 1,
          size: 20,
          pages: 1,
        },
      }),
    });
  });

  await page.route(`**/api/v1/statements/${statementId}/status`, async (route) => {
    if (route.request().method() === "PATCH") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ success: true, data: { statement_id: statementId, status: "REVIEWED" } }),
      });
      return;
    }

    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        data: {
          id: statementId,
          filename: "sample-hdfc-statement.csv",
          bank: "hdfc",
          status: "READY_FOR_REVIEW",
        },
      }),
    });
  });

  await page.route(`**/api/v1/statements/${statementId}/transactions?page=1&size=50`, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        data: {
          items: [
            {
              id: "tx-1",
              statement_id: statementId,
              txn_date: "2026-05-01",
              narration: "UPI Payment to Vendor",
              debit: "1200.00",
              credit: null,
              balance: "48800.00",
              confirmed_ledger: "",
              confidence: "0.400",
            },
            {
              id: "tx-2",
              statement_id: statementId,
              txn_date: "2026-05-03",
              narration: "NEFT Received",
              debit: null,
              credit: "10000.00",
              balance: "58800.00",
              confirmed_ledger: "Sales",
              confidence: "0.900",
            },
          ],
          total: 2,
          page: 1,
          size: 50,
          pages: 1,
        },
      }),
    });
  });

  await page.route(`**/api/v1/statements/${statementId}/transactions/tx-1`, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ success: true, data: { id: "tx-1", narration: "Updated vendor payment" } }),
    });
  });

  await page.route(`**/api/v1/statements/${statementId}/exports`, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  await page.route(`**/api/v1/statements/${statementId}`, async (route) => {
    if (route.request().method() === "DELETE") {
      expect(route.request().headers().authorization).toBe("Bearer e2e-token");
      await route.fulfill({ status: 204 });
      return;
    }

    await route.fallback();
  });
});

test("opens review UI and edits a transaction", async ({ page }) => {
  await page.goto("/dashboard");
  await page.getByTestId(`review-button-${statementId}`).click();

  await expect(page.getByTestId("pdf-viewer")).toBeVisible();
  await expect(page.getByTestId("transaction-row").filter({ visible: true })).toHaveCount(2);

  await page.getByText("UPI Payment to Vendor").first().click();
  await page.getByRole("textbox").last().fill("Updated vendor payment");
  await page.keyboard.press("Enter");

  await expect(page.getByText("Saved")).toBeVisible();
  await page.getByRole("button", { name: "Mark Reviewed" }).click();
  await expect(page.getByText("REVIEWED")).toBeVisible();
});

test("downloads exports with a signed URL", async ({ page }) => {
  await page.route(`**/api/v1/statements/${statementId}/export`, async (route) => {
    expect(route.request().headers().authorization).toBe("Bearer e2e-token");
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        export_id: "export-1",
        statement_id: statementId,
        format: "csv",
        status: "READY",
        download_url: "/v1/exports/export-1/download?download_token=signed-e2e-token",
        filename: "hdfc_2026-06-12_csv.csv",
        created_at: "2026-06-12T00:00:00",
        idempotent: false,
      }),
    });
  });

  await page.route("**/api/v1/exports/export-1/download?download_token=signed-e2e-token", async (route) => {
    expect(route.request().url()).toContain("download_token=signed-e2e-token");
    await route.fulfill({
      contentType: "text/csv",
      headers: {
        "content-disposition": 'attachment; filename="hdfc_2026-06-12_csv.csv"',
      },
      body: "date,narration,amount\n2026-05-01,UPI Payment,1200\n",
    });
  });

  await page.goto(`/dashboard/review/${statementId}`);
  await page.getByRole("button", { name: "Export" }).click();
  await page.getByRole("button", { name: "CSV" }).click();
  await page.getByRole("button", { name: "Export CSV" }).click();

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download CSV" }).click();
  const download = await downloadPromise;

  expect(download.suggestedFilename()).toBe("hdfc_2026-06-12_csv.csv");
});

test("deletes a statement with the auth token", async ({ page }) => {
  page.on("dialog", async (dialog) => {
    expect(dialog.message()).toContain("Delete this statement?");
    await dialog.accept();
  });

  await page.goto("/dashboard");
  await expect(page.getByText("sample-hdfc-statement.csv")).toBeVisible();
  await page.getByRole("button", { name: "Delete statement" }).click();

  await expect(page.getByText("sample-hdfc-statement.csv")).toBeHidden();
});
