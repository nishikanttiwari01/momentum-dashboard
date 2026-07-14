# Mutual-Fund Table Sorting Design

## Objective

Add clear, client-side sorting to every meaningful data column in the Portfolio mutual-funds table without changing its data source, expanded NAV charts, transaction actions or external links.

## Interaction

- Fund, Category, NAV, 1M, 6M, 1Y, Off 1Y high, Invested, Value, XIRR, Avg NAV and Gain / loss headers are sortable.
- Action and Links remain unsortable.
- The initial table preserves the workbook/API order and shows no active sort.
- Clicking a sortable header activates ascending order; clicking it again switches to descending order.
- Clicking a different sortable header starts that column in ascending order.
- Material UI `TableSortLabel` provides the active-column and direction indicator.
- Header controls remain keyboard accessible and expose the active sort direction to assistive technology.

## Sorting Rules

- Fund and Category compare case-insensitively with locale-aware text ordering.
- Numeric columns compare their raw numeric values rather than formatted display strings.
- Gain / loss sorts by the raw gain amount, not the displayed gain percentage.
- Missing or non-finite values always appear after populated values in both ascending and descending order.
- Sorting is stable: equal values retain their original API order.

## Component and Data Flow

The change remains in the Portfolio frontend. A focused sorting helper will map each sortable column to its raw `Instrument` value and return a stable sorted copy of the funds array. `Portfolio` stores the active key and direction, derives `sortedFunds`, and renders the existing fund row plus its optional expanded chart row from that sorted array.

The expanded fund identity remains keyed by `f.id`, so sorting cannot detach a chart from its fund. Sorting does not close the expanded chart; it moves together with its parent fund row.

No backend, API, workbook or CSV changes are required.

## Testing and Validation

- Unit tests cover text sorting, numeric ascending/descending, missing values last in both directions, stable ties and the initial unsorted order.
- A component/source regression test confirms sortable headers use `TableSortLabel` while Action and Links remain plain headers.
- Existing portfolio tests remain green.
- The production build succeeds.
- Browser validation clicks at least Fund, Invested and XIRR headers, verifies direction changes, and confirms an expanded chart stays attached to its fund after sorting.
