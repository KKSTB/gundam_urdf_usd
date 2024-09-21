# isaac_lab_gundam_usd
USD files converted and edited from isaac_lab_gundam_robot_urdf, used by IsaacLabGundam

How to try your own Isaac Lab Gundam RX-78 (Ubuntu):
1. Install Isaac Sim that matches with the Isaac Lab version (https://docs.omniverse.nvidia.com/isaacsim/latest/installation/install_workstation.html) (currently 4.2.0)
2. Create a folder "gundam" under home
3. Clone [isaac_lab_gundam_usd repo](https://github.com/KKSTB/isaac_lab_gundam_usd.git)
4. Clone [IsaacLabGundam](https://github.com/KKSTB/IsaacLabGundam.git)
5. Follow isaac lab normal installation (i.e. https://isaac-sim.github.io/IsaacLab/source/setup/installation/binaries_installation.html#creating-the-isaac-sim-symbolic-link and https://isaac-sim.github.io/IsaacLab/source/setup/installation/binaries_installation.html#installation)
6. To train: `./isaaclab.sh -p source/standalone/workflows/rsl_rl/train.py --task Isaac-Velocity-Rough-Gundam-RX78-v0 --headless`
7. To play the trained model: `./isaaclab.sh -p source/standalone/workflows/rsl_rl/play.py --task Isaac-Velocity-Rough-Gundam-RX78-v0 --num_envs 256`

So far the Gundam can only stand but not walk...

Files:
1. usd/GGC_TestModel_rx78_20170112_10.usd: a 1:10 model of RX-78, with fixed mimic joints (due to crashes during isaac lab training), reduced joint effort limit, and zero joint damping and friction
3. scripts/export_utils.py: edited export_utils.py in $HOME/.local/share/ov/pkg/isaac-sim-4.2.0/extscache/omni.kit.widget.stage-2.11.2+10a4b5c0/omni/kit/widget/stage/, so that prims are in the correct prim path (https://forums.developer.nvidia.com/t/export-usd-model-from-usd-composer-isaac-sim/258436)
