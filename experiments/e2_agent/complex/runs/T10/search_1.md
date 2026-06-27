# T10 — Search Pass 1: Exhaustive Enumeration

Task: design the control regime keeping a commercial greenhouse continuously within the crop's viable
envelope (T, RH, CO₂, PAR, irrigation) across day/night and weather swings, with actuator coupling rules.

---

## Domain Primitives

**P1 — Temperature CV** — air dry-bulb temperature at canopy level is the primary thermal controlled variable — *falsifier: setpoint defined at sensor height, not canopy; crops experience a different temperature.*

**P2 — Relative humidity CV** — RH at canopy is the primary moisture-state variable, but it couples with T to yield VPD, the true crop driver — *falsifier: RH controller declares success while VPD is out of crop range.*

**P3 — CO₂ concentration CV** — daytime CO₂ enrichment setpoint (typically 800–1200 ppm) vs. night minimum; ambient fall-back when vents are open — *falsifier: a single ppm setpoint used day and night ignoring vent-state constraints.*

**P4 — PAR / DLI CV** — photosynthetically active radiation as instantaneous flux (µmol m⁻² s⁻¹) and daily light integral (mol m⁻² d⁻¹) are distinct requirements — *falsifier: system tracks only instantaneous PAR, accumulates no DLI, cannot decide when supplemental lighting is done for the day.*

**P5 — Root-zone moisture and EC** — substrate volumetric water content and electrical conductivity (nutrient concentration) are jointly the irrigation state; neither alone is sufficient — *falsifier: irrigation controller acts on moisture alone, EC creeps to salt-stress level silently.*

**P6 — Heating actuator** — hot-water pipe system (rail heat + grow pipes) with variable flow temperature as the manipulated variable, not just on/off — *falsifier: heating modelled as binary; pipe temperature overshoot boosts canopy T past UTL.*

**P7 — Ventilation actuator** — roof vents (and optionally side vents) with continuous aperture 0–100 %; mechanically limited by wind speed — *falsifier: vents modelled as open/closed; intermediate position control absent.*

**P8 — Thermal / shade screens** — dual-function screens: shade screen (PAR reduction) and thermal screen (night insulation); may be same or separate physical screen — *falsifier: design conflates shade and thermal functions; screen position affects both T and PAR simultaneously without being tracked on both axes.*

**P9 — CO₂ injection actuator** — dosing valve with mass-flow control; supply from cylinder or boiler flue gas — *falsifier: dosing treated as binary open/close; flow rate not measured, CO₂ mass balance impossible.*

**P10 — Irrigation / fertigation actuator** — drip or NFT with timing and volume control; fertigation mixes nutrients inline — *falsifier: irrigation volume not measured per cycle; only timing controlled; actual root-zone state unknown after emitter partial clog.*

**P11 — Supplemental lighting actuator** — HPS or LED grow lights with dimming capability; generates heat as a side-effect — *falsifier: lights modelled as ON/OFF only; dimming for T-management not available.*

**P12 — Horizontal airflow fans** — circulation fans create air movement preventing CO₂ and T stratification; not a CV actuator but required for sensor representativeness — *falsifier: fans absent or uncontrolled; sensor readings valid only at measurement point, not at crop canopy.*

**P13 — Outdoor weather station** — sensors for outdoor T, RH, wind speed/direction, global radiation; feedforward input to all subsystems — *falsifier: outdoor station absent; all control is reactive feedback only; cold-front response lags by the thermal inertia of the structure.*

---

## Lifecycle / State

**L1 — Day-period definition** — "day" is defined by sunrise/sunset (astronomical) not by supplemental-light state; all setpoints must track solar day not lighting day — *falsifier: lighting schedule defines day; on a cloudy day with lights on all day, T setback never fires.*

**L2 — Night setback transition** — at end of day, T setpoint drops (night setback) and CO₂ injection stops; the transition ramp rate matters to prevent overshoot — *falsifier: instant setpoint step causes integral windup; heating overshoots T in the "cool-down" direction.*

**L3 — Dawn transition** — at sunrise, CO₂ injection resumes (before vents open, to pre-charge); T setpoint rises; shading may deploy for direct-beam protection — *falsifier: CO₂ injection delayed until T setpoint reached; first hour of daylight photosynthesis CO₂-limited.*

**L4 — Crop growth stage** — setpoints for T, RH, DLI, and EC differ by growth stage (seedling / vegetative / generative / harvest); the schedule must advance automatically or by operator confirmation — *falsifier: static setpoints; crop grown beyond vegetative optimum without setpoint update.*

**L5 — DIF management** — day/night temperature difference (DIF) controls stem elongation; the DIF target must constrain both day and night setpoints jointly — *falsifier: day setpoint raised without corresponding night setpoint review; DIF grows out of morphology target.*

**L6 — Continuous operation / no gaps** — the control regime must be active 24 h/day with no uncontrolled intervals between schedule blocks — *falsifier: schedule blocks have gaps at midnight or crop-stage boundaries; T drifts uncontrolled.*

---

## Components

**C1 — Setpoint manager** — maintains all CV setpoints as time-of-day and crop-stage functions; feeds setpoints to individual controllers — *falsifier: setpoints hard-coded in each controller independently; stage change requires editing multiple controllers.*

**C2 — Per-CV feedback controllers** — one PID (or equivalent) per CV (T, RH, CO₂, PAR, moisture); each reads its sensor and drives its primary actuator — *falsifier: single monolithic controller couples all CVs; interaction bugs impossible to isolate.*

**C3 — Interlock / coupling rule engine** — the layer that prevents one controller's action from violating another CV's bounds; sits above individual controllers — *falsifier: controllers are purely decoupled PIDs; no layer arbitrates conflicting demands.*

**C4 — Alarm and safety layer** — monitors all CVs for bound violations, CO₂ safety threshold, sensor dropout; triggers alarms and safe-state fallbacks independently of the control layer — *falsifier: alarms implemented inside controller logic; a controller failure disables alarms too.*

**C5 — Sensor validation layer** — detects stuck readings, out-of-range values, rate-of-change anomalies; substitutes fallback value or raises fault — *falsifier: raw sensor values fed directly to controllers; a stuck humidity sensor at 45 % causes constant vent-open command in high-RH conditions.*

**C6 — Logging / historian** — time-series storage for all sensor readings and actuator states at sufficient resolution (≥1 min) for post-hoc diagnosis — *falsifier: no log; transient excursions invisible; root-cause analysis of crop loss impossible.*

---

## Global Invariants

**G1 — Simultaneous viability envelope** — all five CVs must be within crop bounds simultaneously at all times, not each in isolation — *falsifier: each CV independently in range; VPD (T×RH joint) out of range not detected.*

**G2 — No actuator conflict escalation** — when two controllers issue opposing demands (e.g., heating and cooling via ventilation simultaneously), the regime must have a defined priority or blending rule — *falsifier: simultaneous heating and vent-opening; both run at maximum, wasting energy and producing T oscillation.*

**G3 — Energy balance consistency** — heat input = heat losses + heat stored; the control regime must not structurally require more heating capacity than installed — *falsifier: setpoints designed without capacity analysis; on design-day outdoor conditions, T setpoint is physically unreachable.*

**G4 — Water balance consistency** — irrigation volume must equal crop transpiration + drainage target; EC must stay bounded under the fertigation strategy — *falsifier: irrigation controller ignores drainage faction; EC accumulates without leachate check.*

**G5 — CO₂ mass balance feasibility** — CO₂ setpoint must be achievable given injection rate, greenhouse volume, and leakage/vent state — *falsifier: CO₂ setpoint set to 1200 ppm with vents fully open; impossible to reach; controller saturates injection valve permanently.*

**G6 — VPD as a derived global constraint** — VPD = f(T, RH) must be within crop range; it is not controlled directly but must be monitored as a joint output of T and RH controllers — *falsifier: T controller and RH controller each within bounds; VPD nevertheless outside range; no alarm fires.*

**G7 — Photoperiod integrity** — cumulative light-on hours per 24 h must match crop photoperiod requirement; supplemental light and shading together define this — *falsifier: shading cuts natural light period short; supplemental light not extended to compensate; photoperiod shortens inadvertently.*

**G8 — Thermal screen night humidity buildup** — closing thermal screen at night traps moisture; humidity must be managed under closed-screen conditions without relying on full ventilation — *falsifier: RH controller opens vents to manage humidity but thermal screen is closed and also closed to outside air; control action is ineffective or damages screen.*

---

## Cross-Component Interaction Seams

**S1 — Ventilation ↔ Temperature** — vent opening in cold weather reduces T; heating must compensate or vent aperture is limited by a minimum-T interlock — *falsifier: RH controller opens vents fully; T drops below LTL; no interlock prevents it.*

**S2 — Ventilation ↔ CO₂** — open vents flush CO₂ to ambient; CO₂ injection while vents are open is partially or wholly wasted — *falsifier: CO₂ controller injects at full rate while vents are at 80 % aperture; CO₂ never reaches setpoint; supply cylinder depleted rapidly.*

**S3 — Ventilation ↔ Humidity (reverse failure)** — when outdoor dewpoint exceeds indoor dewpoint, ventilation raises RH rather than lowers it; the controller must detect this and switch strategy — *falsifier: RH > setpoint triggers vent opening regardless of outdoor humidity; on a foggy morning, indoor RH rises further.*

**S4 — Heating ↔ Humidity (drying via sensible heat)** — raising T with constant absolute humidity lowers RH; heating can be used to assist humidity reduction but risks T overshoot — *falsifier: heating used aggressively for humidity control pushes T past UTL; T alarm fires because of RH strategy.*

**S5 — Shading ↔ Temperature** — closing shade screen reduces solar heat gain but also reduces PAR; the screen position represents a T/PAR tradeoff requiring joint bounds check — *falsifier: T controller closes shade to 100 % to prevent overheating; PAR drops below crop minimum; no PAR-floor interlock on shading.*

**S6 — Shading ↔ CO₂** — heavy shading reduces photosynthesis; CO₂ uptake falls; if CO₂ injection is running it will overshoot setpoint because sink is gone — *falsifier: CO₂ controller keeps injecting at daytime rate while shading screen is fully closed; CO₂ accumulates past enrichment setpoint.*

**S7 — Supplemental lighting ↔ Temperature** — grow lights generate substantial heat (HPS ~60 % heat); activating lights for PAR/DLI raises T — *falsifier: lighting controller activates full capacity on a warm overcast day; T rises past UTL; T alarm fires; lights must be dimmed or staggered, but no coupling rule exists.*

**S8 — Irrigation ↔ Humidity** — irrigation increases root-zone evaporation and crop transpiration, raising absolute humidity in the canopy zone; high irrigation frequency sustains high RH — *falsifier: RH controller vents while irrigation cycles run; RH never drops to setpoint because irrigation evaporation maintains high moisture input; two controllers fight each other.*

**S9 — CO₂ injection ↔ PAR (photosynthetic sink)** — CO₂ enrichment is only beneficial when PAR is sufficient for photosynthesis to use it; injection at night or under heavy shading yields no crop benefit — *falsifier: CO₂ controller injects to setpoint at night; CO₂ accumulates (no plant sink); waste with no agronomic gain.*

**S10 — Thermal screen ↔ Humidity (night condensation)** — closed thermal screen traps moisture; RH rises toward 100 %; condensation on plants and structures increases disease risk — *falsifier: thermal screen closed all night; RH climbs past 90 %; no humidity control action taken because vents are the only humidity actuator and they conflict with the closed screen.*

**S11 — Supplemental lighting ↔ DIF** — lighting extending into pre-dawn or early morning shifts the effective "day start," compressing the cool morning period that contributes to DIF — *falsifier: DLI catch-up lighting runs 02:00–06:00; morning T setback overlaps with "day" as defined by lights; DIF is halved.*

**S12 — Heating pipe temperature ↔ Condensation (local humidity)** — if pipe surface temperature is below dewpoint, condensation forms on pipes and drips onto crop; pipe temperature setpoint must stay above local dewpoint — *falsifier: pipe T lowered for energy saving on a high-humidity night; dewpoint exceeds pipe surface temperature; drip condensation promotes botrytis.*

**S13 — Outdoor wind speed ↔ Ventilation actuator** — above a wind threshold, roof vents must be limited or closed to prevent structural damage and uncontrolled cold infiltration — *falsifier: vent controller ignores wind speed; in gale conditions, vents open fully for T control; structure is damaged and T crashes.*

**S14 — CO₂ injection ↔ Worker safety interlock** — CO₂ above ~5000 ppm is hazardous; if injection malfunctions or is over-set, a safety cut-off independent of the crop controller must activate — *falsifier: CO₂ set to 1500 ppm; sensor fault reads 1000 ppm; injection continues past 5000 ppm; worker enters without alarm.*

**S15 — Outdoor radiation sensor ↔ Supplemental lighting** — cloud cover detected by outdoor pyranometer triggers supplemental light activation; pyranometer fouling or shading by dirt reads falsely low → lights ON unnecessarily → T rises — *falsifier: PAR sensor dirty; lights activate on a clear day; T pushed above UTL; no cross-check with outdoor global radiation.*

**S16 — Ventilation ↔ CO₂ × Heating (three-way conflict)** — cold outside + high humidity + depleted CO₂: ventilation would address humidity and CO₂ replenishment but would crash T; heating would compensate but energy cost is high; all three must be traded off by a priority rule — *falsifier: no three-way priority rule; individual controllers conflict; oscillation or deadlock.*

**S17 — Irrigation timing ↔ Day/night state** — most crops must not receive irrigation at night (root rot, high-humidity spike); the irrigation controller must respect the day/night interlock even if moisture falls below threshold — *falsifier: moisture sensor crosses threshold at 23:00; irrigation fires; nighttime RH spikes; root rot risk increases.*

**S18 — Setpoint schedule clock ↔ All controllers** — all setpoint transitions (day/night, crop stage) depend on system clock accuracy; clock drift or DST error shifts all transitions — *falsifier: DST change not handled; all setpoints transition one hour early/late; DIF disrupted, CO₂ injection starts in darkness.*

**S19 — Heating capacity ↔ Ventilation minimum** — minimum ventilation for CO₂ and humidity requires some vent opening even in extreme cold; heating must have enough capacity to cover the heat loss from minimum ventilation — *falsifier: minimum vent opening on a -15 °C day exceeds heating capacity; T falls below LTL; minimum vent cannot be honored without crop loss.*

**S20 — Horizontal airflow fans ↔ Sensor representativeness** — without active mixing, sensors measure a stratified layer; CO₂ and T sensor readings may not represent canopy conditions — *falsifier: fans off at night for energy saving; CO₂ sensor near ridge reads high; canopy CO₂ is depleted; no remedial injection.*

**S21 — Screen position ↔ Vent operation** — thermal screen and roof vents may conflict mechanically (screen must be open to allow vent operation in some greenhouse designs) — *falsifier: vent controller opens vents while screen is closed; screen mechanism is damaged or vent cannot fully open; airflow control is impaired.*

---

## Edge / Boundary Cases

**E1 — Heating capacity exhaustion** — outdoor temperature so extreme that heating cannot maintain LTL despite maximum output; regime must have a controlled minimum-T fallback and alarm, not silent crop loss — *falsifier: no alarm at heating saturation; crop freezes without notification.*

**E2 — Cooling capacity exhaustion** — summer peak: full vent aperture + full shading + fogging still cannot maintain UTL; requires an overtemperature alarm with documented crop-loss threshold — *falsifier: no UTL alarm; crop heat stress accumulates silently.*

**E3 — Outdoor humidity inversion (RH_out > RH_in)** — ventilation is counterproductive for humidity reduction; regime must detect this condition and switch to heating-only or accept elevated RH temporarily — *falsifier: RH controller opens vents regardless; outdoor fog drives indoor RH to 100 %.*

**E4 — Power outage / UPS fail-over** — all actuators must have defined fail-safe positions (vents partially open for temperature, heating off, lights off); the regime must specify and test these — *falsifier: fail-safe positions undefined; on power loss some vents slam open in cold weather; crop freezes.*

**E5 — Single sensor failure** — one T, RH, or CO₂ sensor fails (stuck, OOR, dropout); controller must detect and switch to fallback or conservative default, not continue on bad data — *falsifier: stuck RH sensor at 30 %; vents remain closed in 95 % RH conditions; disease outbreak.*

**E6 — CO₂ supply exhaustion** — supply cylinder or line pressure drops to zero; injection valve open but no CO₂ flows; no flow feedback → controller reports setpoint achieved — *falsifier: no CO₂ flow meter or supply-pressure sensor; supply runs out undetected; crops CO₂-limited for days.*

**E7 — Irrigation emitter clog** — partial or full clog at drip emitters; moisture controller sees no change in substrate moisture and continues calling for more irrigation, which cannot reach root zone — *falsifier: no flow confirmation at emitter level; clog undetected; root zone dries while controller believes irrigation is working.*

**E8 — Sensor spatial heterogeneity** — a single T/RH/CO₂ sensor cannot represent a large multi-span greenhouse; zone variation can be large, especially near vents or heat pipes — *falsifier: single-point sensing assumed representative; cold corners or hot zones develop undetected.*

**E9 — Rain on PAR sensor** — rain droplets on quantum sensor surface attenuate reading; regime falsely determines low light and activates supplemental lighting — *falsifier: no rain flag from weather station to suppress PAR-triggered lighting; lights run in rain, raise T unnecessarily.*

**E10 — Wind-induced vent flutter** — at threshold wind speed, vent actuators fight wind buffeting; mechanical wear and unpredictable aperture result — *falsifier: no wind-speed limit on vent operation; actuator cycle count exceeds design life; mechanical failure.*

**E11 — Simultaneous maximum demands** — all five CVs simultaneously approach adverse limits (cold + high humidity + low CO₂ + low light + dry substrate); the priority resolution of the interlock engine must be defined — *falsifier: interlock engine has no total-ordering of priorities; undefined behavior under combined stress.*

**E12 — DST and leap-second transitions** — system clock jumps cause schedule gaps or double-execution of time-based rules — *falsifier: DST not handled; at spring-forward the clock skips one hour of schedule; setpoints frozen for an hour.*

**E13 — Crop canopy temperature vs. air temperature** — in high-radiation conditions, canopy surface temperature can exceed air temperature by 3–8 °C due to radiation load; air T sensor within spec but crop experiencing heat stress — *falsifier: no canopy temperature correction or infrared sensor; T control declared success; crop thermally stressed.*

---

## Silent Failure Modes

**F1 — Humidity sensor calibration drift** — RH sensor drifts 10 % low over months; regime infers RH is acceptable and never opens vents for humidity; actual high RH drives disease — *falsifier: no scheduled sensor recalibration or cross-check with secondary sensor.*

**F2 — CO₂ NDIR sensor zero-drift** — CO₂ sensor reads 150 ppm below true value; controller injects to apparent setpoint but actual CO₂ exceeds setpoint or stays below crop optimum — *falsifier: no reference-gas span calibration schedule.*

**F3 — Heating pipe fouling** — scale accumulates in pipes; flow resistance rises; thermal output drops; T setpoint takes longer to reach; controller compensates silently by increasing flow temperature — *falsifier: no heat-delivery performance metric; pipe efficiency degrades 20 % before anyone notices.*

**F4 — PAR sensor soiling** — dust or condensate on quantum sensor attenuates reading; regime infers low PAR and runs supplemental lighting unnecessarily; T rises — *falsifier: no cleaning schedule or cross-check with outdoor radiation model.*

**F5 — PID integral windup** — heating or ventilation actuator saturates during extreme conditions; integral term accumulates; on recovery, large overshoot occurs — *falsifier: no anti-windup implemented; T overshoots UTL after a cold snap ends.*

**F6 — VPD out-of-range without individual-CV alarm** — T within [18–26 °C], RH within [60–90 %]; but VPD = 0.2 kPa (under-stress) or 2.5 kPa (over-stress); no alarm fires because each CV is individually in range — *falsifier: no VPD monitor; crop transpiration disrupted without triggering any alert.*

**F7 — Irrigation EC creep** — each irrigation cycle adds nutrients; drainage removes some; if drainage fraction is insufficient, EC accumulates over weeks to osmotic-stress levels — *falsifier: no EC trend alarm; EC crosses 6.0 mS/cm silently; yield loss attributed elsewhere.*

**F8 — Screen drive motor slip** — screen position reported by encoder as 70 % but mechanical position is 40 % due to drive slip; T and PAR calculations based on wrong screen state — *falsifier: no end-stop calibration or torque monitoring; screen position assumed reliable.*

**F9 — CO₂ enrichment during roof-leak infiltration** — structural crack or open louver allows unmetered air infiltration; CO₂ concentration depressed; controller injects continuously but reading never reaches setpoint — *falsifier: CO₂ setpoint never reached despite maximum injection; no "injection saturation" alarm.*

**F10 — Nighttime irrigation from threshold exceedance** — moisture sensor threshold crossed at night; no day/night interlock in irrigation code path; drip fires; RH spikes; no RH alarm because spike is brief and sensor has slow response — *falsifier: no irrigation-night interlock; night RH spike not captured by 5-min averaging.*

---

## Scope Boundaries

**B1 — Pest and disease management** — out of scope: biological control agents, pesticide application; IN if a CV excursion (RH > 90 %) directly enables disease — the climate control regime must prevent those excursions — *what pulls it in: any CV setpoint defined partly to prevent disease incidence.*

**B2 — Specific crop nutrition chemistry** — fertilizer recipe (N:P:K ratios) is out of scope; EC and pH as control targets for irrigation are IN scope as they couple to moisture control — *what pulls it in: EC target change requires irrigation controller reconfiguration.*

**B3 — Greenhouse structural design** — structural integrity of frames, glass, screens is out of scope; mechanical limits on vent aperture and screen speed that constrain actuator setpoints are IN scope — *what pulls it in: wind load limits on vent aperture directly constrain ventilation strategy.*

**B4 — Long-term crop scheduling and harvest planning** — out of scope; the current crop-stage setpoints are IN scope as they must be updated at stage transitions — *what pulls it in: automatic stage advancement requires a growth model or calendar trigger.*

**B5 — Grid / energy market optimization** — peak demand curtailment and tariff-based heating scheduling are out of scope for the core regime; if implemented, they add a constraint on heating and lighting that can conflict with CV bounds — *what pulls it in: if demand-response cuts heating during a cold night, T violation follows.*

**B6 — CO₂ source generation (boiler / cylinder management)** — out of scope; monitoring supply availability (pressure sensor, low-supply alarm) is IN scope as supply failure is a silent failure mode (F9 variant) — *what pulls it in: boiler-sourced CO₂ has variable purity; flue-gas treatment must be verified.*

**B7 — Worker access and entry interlocks** — occupational safety for CO₂ (S14) and high-heat conditions is a safety requirement, not an agronomic one; still IN scope as a mandatory interlock on the CO₂ controller — *what pulls it in: any CO₂ injection above 5000 ppm threshold.*
