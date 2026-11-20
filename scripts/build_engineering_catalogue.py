"""Generate original project proposal variants, not published student research."""
import json
from pathlib import Path

DEPARTMENTS = {
 'Computer Engineering': 'edge camera|RFID access terminal|wireless sensor gateway|smart classroom controller|wearable activity logger|embedded weather station|robot navigation controller|parking occupancy node|remote laboratory board|battery powered data logger',
 'Software Engineering': 'course registration service|laboratory booking service|equipment maintenance platform|engineering document repository|project supervision portal|campus transport service|inventory tracking service|research data pipeline|accessible learning application|student helpdesk service',
 'Electrical Engineering': 'low voltage solar charger|battery discharge test bench|DC motor drive|microgrid simulator|energy metering node|LED lighting controller|solar panel tracker|transformer thermal simulator|power quality simulator|load scheduling controller',
 'Electronic Engineering': 'temperature measurement circuit|strain measurement circuit|optical pulse test rig|capacitive level sensor|ultrasonic distance module|audio amplifier test bench|digital filter board|wireless telemetry module|instrumentation amplifier|electronic load simulator',
 'Telecommunications Engineering': 'campus Wi-Fi simulator|LoRa sensor network|mesh routing simulator|optical link simulator|radio channel simulator|antenna positioning rig|packet scheduling simulator|voice traffic simulator|spectrum occupancy dataset|emergency communication simulator',
 'Mechanical Engineering': 'bearing vibration rig|heat exchanger simulator|fan performance rig|pump test loop|belt drive rig|thermal storage simulator|vibration isolation rig|compressed air simulator|gearbox test model|solar air heater',
 'Mechatronics Engineering': 'line following robot|sorting conveyor model|robot gripper|pan tilt camera rig|automated dispensing rig|balancing robot model|pick and place simulator|servo positioning rig|warehouse robot simulator|automated inspection station',
 'Civil Engineering': 'bridge vibration model|concrete curing monitor|water distribution simulator|stormwater drainage model|traffic intersection simulator|building energy model|slope stability simulator|construction progress tracker|pavement condition dataset|structural deflection rig',
 'Chemical Engineering': 'mixing tank simulator|distillation column simulator|heat recovery simulator|adsorption column model|reactor temperature simulator|membrane filtration model|batch process scheduler|fluid mixing model|drying process simulator|process water reuse model',
 'Agricultural Engineering': 'drip irrigation rig|greenhouse climate monitor|soil moisture logger|grain storage monitor|crop drying simulator|aquaculture monitoring rig|livestock water monitor|seed sorting model|farm machinery maintenance platform|rainwater irrigation planner',
 'Biomedical Engineering': 'synthetic ECG processing pipeline|prosthetic hand simulator|rehabilitation exercise simulator|hospital equipment tracker|wheelchair navigation simulator|incubator thermal model|synthetic gait dataset|medical device maintenance platform|assistive reading prototype|synthetic respiratory signal pipeline',
 'Environmental Engineering': 'air quality monitoring node|water quality test rig|waste collection planner|noise mapping platform|flood level monitoring model|recycling classification dataset|wastewater treatment simulator|urban heat mapping platform|landfill gas simulator|rainwater harvesting model',
 'Materials Engineering': 'corrosion monitoring model|composite beam simulator|heat treatment simulator|surface defect image dataset|material selection platform|tensile test dataset|polymer cooling simulator|fatigue life dataset|coating inspection dataset|thermal conductivity rig',
 'Industrial Engineering': 'production scheduling simulator|warehouse picking simulator|equipment downtime tracker|assembly line simulator|quality inspection dataset|supply chain simulator|workstation ergonomics model|maintenance scheduling platform|queue management simulator|spare parts inventory system',
 'Aerospace Engineering': 'flight dynamics simulator|airfoil analysis model|drone battery test simulator|attitude estimation simulator|propeller test simulator|aircraft maintenance planner|wind tunnel data pipeline|landing gear vibration model|satellite thermal simulator|flight telemetry pipeline',
 'Marine Engineering': 'ship engine thermal simulator|bilge monitoring model|ballast tank simulator|propeller performance model|hull inspection dataset|marine battery simulator|vessel maintenance platform|wave energy simulator|harbour traffic simulator|underwater telemetry simulator',
 'Petroleum Engineering': 'pipeline leak simulator|well pressure simulator|reservoir production model|drilling vibration dataset|pump condition simulator|gas lift simulator|separator process model|pipeline corrosion dataset|water injection simulator|production maintenance planner',
 'Mining Engineering': 'mine ventilation simulator|haul truck scheduling model|conveyor condition monitor|ore sorting dataset|mine water pumping model|slope displacement simulator|dust monitoring model|equipment maintenance planner|mine energy scheduling model|mineral processing simulator',
 'Automotive Engineering': 'electric vehicle range simulator|battery thermal simulator|braking distance simulator|suspension vibration model|tyre pressure simulator|vehicle diagnostics dataset|charging station scheduler|engine cooling model|fleet maintenance platform|driver alertness synthetic dataset',
 'Food and Bioprocess Engineering': 'cold chain temperature logger|food drying simulator|fermentation temperature simulator|packaging inspection dataset|pasteurisation thermal simulator|food traceability platform|storage humidity monitor|bioreactor mixing simulator|process cleaning scheduler|food waste collection planner',
}
METHODS = [
 ('Monitoring and Data Logging', 'hardware/software', 'Build a timestamped acquisition and dashboard pipeline; where physical access is unavailable use a labelled simulator. Calibrate against a reference and record missing observations.', 'calibration error, missing sample fraction, latency and storage cost', 'Arduino sensor and serial examples', 'https://docs.arduino.cc/built-in-examples/'),
 ('Fault Detection and Diagnosis', 'software', 'Create labelled normal and abnormal operating scenarios. Compare threshold rules against a statistical detector. Separate training and evaluation runs to prevent data leakage.', 'precision, recall, false alarms and detection delay', 'SciPy signal processing tutorial', 'https://docs.scipy.org/doc/scipy/tutorial/signal.html'),
 ('Parameter Optimisation', 'software', 'Define an objective and feasible parameter bounds. Compare a grid search baseline with a numerical optimiser; test sensitivity to uncertain inputs and report constraint violations.', 'objective improvement, runtime and feasibility rate', 'SciPy optimisation tutorial', 'https://docs.scipy.org/doc/scipy/tutorial/optimize.html'),
 ('Simulation and Performance Evaluation', 'software', 'Implement a documented mathematical or discrete event model. Check limiting cases against hand calculations, vary workload and disturbance levels, and compare predictions with independent reference observations.', 'prediction error, computational cost and sensitivity', 'SciPy user guide: integration and interpolation', 'https://docs.scipy.org/doc/scipy/tutorial/'),
 ('Reliability and Maintenance Decision Support', 'software', 'Build a component and failure history schema. Use explicitly labelled synthetic records if real logs are unavailable. Compare fixed interval maintenance with condition based prioritisation on held-out scenarios.', 'downtime, inspection effort and missed failures', 'SciPy user guide: statistics and optimisation', 'https://docs.scipy.org/doc/scipy/tutorial/'),
]

def build():
    root = Path(__file__).resolve().parents[1]
    folder = root / 'backend/app/knowledge/corpus'
    titles = set()
    count = 0
    for index, (department, assets) in enumerate(DEPARTMENTS.items(), 1):
        sections = []
        for asset in assets.split('|'):
            for method, kind, procedure, metrics, resource, url in METHODS:
                count += 1
                title = f'{method} for a {asset.title()}'
                assert title not in titles
                titles.add(title)
                content = (f'ENG-{count:04d}: {title}. Department: {department}. Type: {kind}. '
                    f'Original suggested final year project, not a completed student thesis. '
                    f'Aim: develop and evaluate {method.lower()} for {asset}. '
                    f'Method: {procedure} '
                    f'Scope: one {asset} prototype or model, one baseline and three test conditions. '
                    f'Tools: Python, CSV/SQLite and a plotting dashboard; sensor projects may use a low voltage microcontroller with suitable calibrated sensors. '
                    f'Evaluation: {metrics}. Set acceptance targets with a supervisor before collecting results. '
                    f'Deliverables: requirements, system diagram, reproducible code, labelled test data, results and limitations. '
                    f'Learning resource: {resource}: {url}. This explains the implementation method, not proof that this proposed project has been completed. '
                    f'Use supervised bench models or simulation for hazardous systems; biomedical proposals are nonclinical. Establish department-specific theory and feasibility with the supervisor.')
                sections.append([f'ENG-{count:04d} {method}', content])
        source = dict(id=f'engineering-proposals-v1-{index:02d}', title=f'{department}: 50 Final Year Project Proposals',
            author='EduMind generated project catalogue', license='Original generated proposals; linked resources retain their own terms',
            license_url='https://github.com/sumiEmpire001/edumind-ai', url='https://github.com/sumiEmpire001/edumind-ai/blob/main/docs/engineering-catalogue.md',
            changes='Original structured proposal variants. Resource links only; no textbook text copied. Not independently validated student research.',
            discipline=department, sections=sections)
        (folder / f'engineering-{index:02d}.json').write_text(json.dumps([source], indent=2)+'\n')
    assert count == 1000
    print(f'Validated {count} unique titles across {len(DEPARTMENTS)} departments')

if __name__ == '__main__':
    build()
