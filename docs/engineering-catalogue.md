# Engineering project proposal catalogue

1,000 original generated proposal variants: 20 disciplines, 10 systems per discipline and five investigation approaches per system. These are not collected student dissertations or independently validated research projects. Coverage is broad, not a claim to enumerate every department worldwide.

Each entry supplies an aim, practical method, bounded scope, tools, evaluation metrics, deliverables and an implementation-resource URL. Resources teach the proposed method; they are not citations proving results. The catalogue does not include copied textbooks. Domain theory, novelty, component selection, budget and acceptance criteria require supervisor review. Synthetic data must remain labelled; simulations do not establish real-world safety or clinical validity.

The five approaches are monitoring, diagnosis, optimisation, simulation and reliability. Some software-first systems need simulated telemetry rather than physical sensors. Hardware projects require equipment-specific calibration and design beyond the general proposal.

Run `python scripts/build_engineering_catalogue.py` to regenerate. The existing idempotent starter importer loads 20 collections; existing or removed collection IDs remain untouched. This is searchable proposal knowledge, not model-weight training. Knowledge API role restrictions remain unchanged.

Resources verified November 20, 2026:
- https://docs.arduino.cc/built-in-examples/
- https://docs.scipy.org/doc/scipy/tutorial/signal.html
- https://docs.scipy.org/doc/scipy/tutorial/optimize.html
- https://docs.scipy.org/doc/scipy/tutorial/

Example: ask Study Chat for a mechanical engineering bearing vibration fault detection project, then request objectives, methodology and an evaluation plan. Confirm that the cited catalogue passage matches the answer.
