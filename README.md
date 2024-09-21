# isaac_lab_gundam_usd
USD files converted and edited from isaac_lab_gundam_robot_urdf, to be used by IsaacLabGundam

How to try your own Isaac Lab Gundam RX-78 (Ubuntu):
1. Create a folder "gundam" under home
2. Clone [isaac_lab_gundam_usd repo](https://github.com/KKSTB/isaac_lab_gundam_usd.git)
3. Clone [IsaacLabGundam](https://github.com/KKSTB/IsaacLabGundam.git)
4. Follow isaac lab normal installation (i.e. https://isaac-sim.github.io/IsaacLab/source/setup/installation/binaries_installation.html#creating-the-isaac-sim-symbolic-link and https://isaac-sim.github.io/IsaacLab/source/setup/installation/binaries_installation.html#installation)
5. To train: `./isaaclab.sh -p source/standalone/workflows/rsl_rl/train.py --task Isaac-Velocity-Rough-Gundam-RX78-v0 --headless`
6. To play the trained model: `./isaaclab.sh -p source/standalone/workflows/rsl_rl/play.py --task Isaac-Velocity-Rough-Gundam-RX78-v0 --num_envs 256`

Files:
1. usd/GGC_TestModel_rx78_20170112_10.usd: a 1:10 model of RX-78, with fixed mimic joints (due to crashes during isaac lab training), reduced joint effort limit, and zero joint damping and friction
3. scripts/export_utils.py: edited export_utils.py in $HOME/.local/share/ov/pkg/isaac-sim-4.2.0/extscache/omni.kit.widget.stage-2.11.2+10a4b5c0/omni/kit/widget/stage/, so that prims are in the correct prim path (https://forums.developer.nvidia.com/t/export-usd-model-from-usd-composer-isaac-sim/258436)
