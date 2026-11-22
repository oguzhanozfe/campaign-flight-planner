# Review a flight calendar

The input describes existing bookings and requested creative flights. A booking has an ID, audience, start date, duration in days and a daily capacity requirement in units. Requests give earliest start, latest **inclusive end**, duration, units and priority from one to five. A single daily-capacity limit applies across audiences.

The planner detects existing audience overlaps and capacity overages before reserving anything. It places higher-priority requests first, favors tighter windows at equal priority and searches for contiguous free days. A request cannot overlap another booking for the same audience. Different audiences can run simultaneously when capacity allows. Rejected-start counts record the first failing rule for each tested date. The schedule is a deterministic first-fit proposal, not an optimal revenue forecast.

Approve individual placements to export an all-day iCalendar file with the original bookings plus approved additions. The iCalendar end date is exclusive. Existing bookings remain visible even if they already collide. Deselection leaves a gap rather than unexpectedly shifting another reviewed flight. No ad-platform order is submitted.
